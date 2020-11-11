from datetime import datetime, date
from .certificate import CommonCriteriaCert, Certificate
from abc import ABC, abstractmethod
from . import helpers as helpers
from pathlib import Path
import shutil
import pandas as pd
from bs4 import BeautifulSoup
import locale
import logging
from typing import Dict
import json


class DatasetJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Certificate):
            return obj.to_dict()
        if isinstance(obj, set):
            return list(obj)
        if isinstance(obj, date):
            return str(obj)
        if isinstance(obj, CommonCriteriaCert.ProtectionProfile):
            return obj.to_dict()
        if isinstance(obj, CommonCriteriaCert.MaintainanceReport):
            return obj.to_dict()
        if isinstance(obj, Dataset):
            return list(obj.certs.values())

        return super().default(obj)


class Dataset(ABC):
    def __init__(self, certs: dict, root_dir: Path, name: str = 'dataset name', description: str = 'dataset_description'):
        self.certs = certs
        self.root_dir = root_dir

        self.timestamp = datetime.now()
        self.sha256_digest = 'not implemented'
        self.name = name
        self.description = description

    def __iter__(self):
        for cert in self.certs.values():
            yield cert

    def __getitem__(self, item: str) -> 'Certificate':
        return self.certs.__getitem__(item.lower())

    def __setitem__(self, key: str, value: 'Certificate'):
        self.certs.__setitem__(key.lower(), value)

    def __len__(self) -> int:
        return len(self.certs)

    def __eq__(self, other: 'Dataset') -> bool:
        return self.certs == other.certs

    def __str__(self) -> str:
        return 'Not implemented'

    def to_json(self):
        pass

    def to_csv(self):
        pass

    def to_dataframe(self):
        pass

    @classmethod
    def from_json(cls):
        pass

    @classmethod
    def from_csv(cls):
        pass

    def dump_to_json(self):
        pass

    @abstractmethod
    def get_certs_from_web(self):
        pass

    def merge(self, certs: Dict[str, 'Certificate']):
        pass


class CCDataset(Dataset):
    @property
    def web_dir(self) -> Path:
        return self.root_dir / 'web'

    html_products = {
        'cc_products_active.html': 'https://www.commoncriteriaportal.org/products/',
        'cc_products_archived.html': 'https://www.commoncriteriaportal.org/products/index.cfm?archived=1',
    }
    html_labs = {'cc_labs.html': 'https://www.commoncriteriaportal.org/labs'}
    csv_products = {
        'cc_products_active.csv': 'https://www.commoncriteriaportal.org/products/certified_products.csv',
        'cc_products_archived.csv': 'https://www.commoncriteriaportal.org/products/certified_products-archived.csv',
    }
    html_pp = {
        'cc_pp_active.html': 'https://www.commoncriteriaportal.org/pps/',
        'cc_pp_collaborative.html': 'https://www.commoncriteriaportal.org/pps/collaborativePP.cfm?cpp=1',
        'cc_pp_archived.html': 'https://www.commoncriteriaportal.org/pps/index.cfm?archived=1',
    }
    csv_pp = {
        'cc_pp_active.csv': 'https://www.commoncriteriaportal.org/pps/pps.csv',
        'cc_pp_archived.csv': 'https://www.commoncriteriaportal.org/pps/pps-archived.csv'
    }

    def merge_certs(self, certs: Dict[str, 'CommonCriteriaCert']):
        """
        Merges dictionary of certificates into the dataset. Assuming they all are CommonCriteria certificates
        """
        will_be_added = {}
        n_merged = 0
        for crt in certs.values():
            if crt not in self:
                will_be_added[crt.dgst] = crt
            else:
                self[crt.dgst].merge(crt)
                n_merged += 1

        self.certs.update(will_be_added)
        logging.info(f'Added {len(will_be_added)} new and merged further {n_merged} certificates to the dataset.')

    def get_certs_from_web(self, keep_metadata: bool = True):
        """
        Downloads all metadata about certificates from CSV and HTML sources
        """
        self.web_dir.mkdir(parents=True, exist_ok=True)

        logging.info('Downloading required csv and html files.')
        html_items = [(x, self.web_dir / y) for y, x in self.html_products.items()]
        csv_items = [(x, self.web_dir / y) for y, x in self.csv_products.items()]
        helpers.download_parallel(html_items, num_threads=8)
        helpers.download_parallel(csv_items, num_threads=8)

        logging.info('Adding CSV certificates to CommonCriteria dataset.')
        csv_certs = self.get_all_certs_from_csv()
        self.merge_certs(csv_certs)

        # TODO: Someway along the way, 3 certificates get lost. Investigate and fix.
        logging.info('Adding HTML certificates to CommonCriteria dataset.')
        html_certs = self.get_all_certs_from_html()
        self.merge_certs(html_certs)

        logging.info(f'The resulting dataset has {len(self)} certificates.')

        if not keep_metadata:
            shutil.rmtree(self.web_dir)

    def get_all_certs_from_csv(self) -> Dict[str, 'CommonCriteriaCert']:
        """
        Creates dictionary of new certificates from csv sources.
        """
        new_certs = {}
        for file in self.csv_products:
            partial_certs = self.parse_single_csv(self.web_dir / file)
            logging.info(f'Parsed {len(partial_certs)} certificates from: {file}')
            new_certs.update(partial_certs)
        return new_certs

    @staticmethod
    def parse_single_csv(file: Path) -> Dict[str, 'CommonCriteriaCert']:
        """
        Using pandas, this parses a single CSV file.
        """
        def get_primary_key_str(row):
            prim_key = row['category'] + row['cert_name'] + row['report_link']
            return prim_key

        csv_header = ['category', 'cert_name', 'manufacturer', 'scheme', 'security_level', 'protection_profiles',
                       'not_valid_before', 'not_valid_after', 'report_link', 'st_link', 'maintainance_date',
                       'maintainance_title', 'maintainance_report_link', 'maintainance_st_link']

        df = pd.read_csv(file, engine='python', encoding='windows-1250')
        df = df.rename(columns={x: y for (x, y) in zip(list(df.columns), csv_header)})

        df['is_maintainance'] = ~df.maintainance_title.isnull()
        df = df.fillna(value='')

        df[['not_valid_before', 'not_valid_after', 'maintainance_date']] = df[['not_valid_before', 'not_valid_after', 'maintainance_date']].apply(pd.to_datetime)

        df['dgst'] = df.apply(lambda row: helpers.get_first_16_bytes_sha256(get_primary_key_str(row)), axis=1)
        df_base = df.loc[df.is_maintainance == False].copy()
        df_main = df.loc[df.is_maintainance == True].copy()

        n_all = len(df_base)
        n_deduplicated = len(df_base.drop_duplicates(subset=['dgst']))
        logging.warning(f'The CSV {file} contains {n_all - n_deduplicated} duplicates by the primary key.')

        df_base = df_base.drop_duplicates(subset=['dgst'])
        df_main = df_main.drop_duplicates()

        profiles = {x.dgst: set([CommonCriteriaCert.ProtectionProfile(y, None) for y in helpers.sanitize_protection_profiles(x.protection_profiles)]) for x in df_base.itertuples()}
        updates = {x.dgst: set() for x in df_base.itertuples()}
        for x in df_main.itertuples():
            updates[x.dgst].add(CommonCriteriaCert.MaintainanceReport(x.maintainance_date.date(), x.maintainance_title, x.maintainance_report_link, x.maintainance_st_link))

        certs = {x.dgst: CommonCriteriaCert(x.category, x.cert_name, x.manufacturer, x.scheme, x.security_level, x.not_valid_before, x.not_valid_after, x.report_link, x.st_link, 'csv', None, None, profiles.get(x.dgst, None), updates.get(x.dgst, None)) for x in df_base.itertuples()}
        return certs

    def get_all_certs_from_html(self) -> Dict[str, 'CommonCriteriaCert']:
        """
        Prepares dictionary of certificates from all html files.
        """
        new_certs = {}
        for file in self.html_products:
            partial_certs = self.parse_single_html(self.web_dir / file)
            logging.info(f'Parsed {len(partial_certs)} certificates from: {file}')
            new_certs.update(partial_certs)
        return new_certs

    @staticmethod
    def parse_single_html(file: Path) -> Dict[str, 'CommonCriteriaCert']:
        """
        Prepares a dictionary of certificates from a single html file.
        """
        def get_timestamp_from_footer(footer):
            locale.setlocale(locale.LC_ALL, 'en_US')
            footer_text = list(footer.stripped_strings)[0]
            date_string = footer_text.split(',')[1:3]
            time_string = footer_text.split(',')[3].split(' at ')[1]
            formatted_datetime = date_string[0] + date_string[1] + ' ' + time_string
            return datetime.strptime(formatted_datetime, ' %B %d %Y %I:%M %p')

        def parse_table(soup: BeautifulSoup, table_id: str, category_string: str) -> Dict[str, 'CommonCriteriaCert']:
            tables = soup.find_all('table', id=table_id)
            assert len(tables) == 1
            table = tables[0]
            rows = list(table.find_all('tr'))
            header, footer, body = rows[0], rows[1], rows[2:]

            # TODO: It's possible to obtain timestamp of the moment when the list was generated. It's identical for each table and should thus only be obtained once. Not necessarily in each table
            # timestamp = get_timestamp_from_footer(footer)

            # TODO: Do we have use for number of expected certs? We get rid of duplicites, so no use for assert expected == actual
            # caption_str = str(table.findAll('caption'))
            # n_expected_certs = int(caption_str.split(category_string + ' – ')[1].split(' Certified Products')[0])
            table_certs = {x.dgst: x for x in [CommonCriteriaCert.from_html_row(row, category_string) for row in body]}

            return table_certs

        cc_cat_abbreviations = ['AC', 'BP', 'DP', 'DB', 'DD', 'IC', 'KM',
                                'MD', 'MF', 'NS', 'OS', 'OD', 'DG', 'TC']
        cc_table_ids = ['tbl' + x for x in cc_cat_abbreviations]
        cc_categories = ['Access Control Devices and Systems',
                         'Boundary Protection Devices and Systems',
                         'Data Protection',
                         'Databases',
                         'Detection Devices and Systems',
                         'ICs, Smart Cards and Smart Card-Related Devices and Systems',
                         'Key Management Systems',
                         'Mobility',
                         'Multi-Function Devices',
                         'Network and Network-Related Devices and Systems',
                         'Operating Systems',
                         'Other Devices and Systems',
                         'Products for Digital Signatures',
                         'Trusted Computing'
                         ]
        cat_dict = {x: y for (x, y) in zip(cc_table_ids, cc_categories)}

        with open(file, 'r') as handle:
            soup = BeautifulSoup(handle, 'html.parser')

        certs = {}
        for key, val in cat_dict.items():
            certs.update(parse_table(soup, key, val))

        return certs
