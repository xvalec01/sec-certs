import os
import re
from datetime import datetime
import locale
import logging
from typing import Dict, List, ClassVar, Collection, TypeVar, Type, Union
import json
from importlib import import_module

import copy
from abc import ABC, abstractmethod
from pathlib import Path
import shutil

from functools import partial
import requests

from tabula import read_pdf
import pandas as pd
from bs4 import BeautifulSoup


from sec_certs.files import search_files
from sec_certs import helpers as helpers
from sec_certs.helpers import find_tables, repair_pdf
from sec_certs.certificate import CommonCriteriaCert, Certificate, FIPSCertificate
from sec_certs.extract_certificates import extract_certificates_keywords
from sec_certs.constants import FIPS_NOT_AVAILABLE_CERT_SIZE
import sec_certs.constants as constants
import sec_certs.download as download
import sec_certs.cert_processing as cert_processing
from sec_certs.serialization import ComplexSerializableType, CustomJSONDecoder, CustomJSONEncoder

logger = logging.getLogger(__name__)


class Dataset(ABC):
    def __init__(self, certs: Dict[str, 'Certificate'], root_dir: Path, name: str = 'dataset name',
                 description: str = 'dataset_description'):
        self.root_dir = root_dir
        self.timestamp = datetime.now()
        self.sha256_digest = 'not implemented'
        self.name = name
        self.description = description
        self.certs = certs

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
        return str(type(self).__name__) + ':' + self.name + ', ' + str(len(self)) + ' certificates'

    def to_dict(self):
        return {'timestamp': self.timestamp, 'sha256_digest': self.sha256_digest,
                'name': self.name, 'description': self.description,
                'n_certs': len(self), 'certs': list(self.certs.values())}

    @classmethod
    def from_dict(cls, dct: Dict):
        certs = {x.dgst: x for x in dct['certs']}
        dset = cls(certs, Path('./'), dct['name'], dct['description'])
        assert len(dset) == dct['n_certs']
        return dset

    def to_json(self, output_path: Union[str, Path]):
        with Path(output_path).open('w') as handle:
            json.dump(self, handle, indent=4, cls=CustomJSONEncoder)

    @classmethod
    def from_json(cls, input_path: Union[str, Path]):
        with Path(input_path).open('r') as handle:
            dset = json.load(handle, cls=CustomJSONDecoder)
        dset.root_path = input_path.parent
        return dset

    @abstractmethod
    def get_certs_from_web(self):
        raise NotImplementedError('Not meant to be implemented by the base class.')

    @abstractmethod
    def convert_all_pdfs(self):
        raise NotImplementedError('Not meant to be implemented by the base class.')

    @abstractmethod
    def download_all_pdfs(self):
        raise NotImplementedError('Not meant to be implemented by the base class.')

    @staticmethod
    def _convert_pdfs_to_txt(pdf_paths: Collection[Path], txt_paths: Collection[Path]):
        assert len(pdf_paths) == len(txt_paths)

        partial_convert_pdf = partial(helpers.convert_pdf_file, options=['-raw'])
        exit_codes = cert_processing.process_parallel(partial_convert_pdf,
                                                      list(zip(pdf_paths, txt_paths)),
                                                      constants.N_THREADS,
                                                      use_threading=False)

        n_successful = len([e for e in exit_codes if e == constants.RETURNCODE_OK])
        logger.info(f'Successfully converted {n_successful} files pdf->txt, {len(exit_codes) - n_successful} failed.')

        for path, e in zip(pdf_paths, exit_codes):
            if e != constants.RETURNCODE_OK:
                logger.info(f'Failed to convert {path}, exit code: {e}')

    @staticmethod
    def _download_parallel(urls, paths, prune_corrupted=True):
        exit_codes = cert_processing.process_parallel(download.download_file,
                                                      list(zip(urls, paths)),
                                                      constants.N_THREADS)
        n_successful = len([e for e in exit_codes if e == requests.codes.ok])
        logger.info(f'Successfully downloaded {n_successful} files, {len(exit_codes) - n_successful} failed.')

        for url, e in zip(urls, exit_codes):
            if e != requests.codes.ok:
                logger.error(f'Failed to download {url}, exit code: {e}')

        if prune_corrupted is True:
            for p in paths:
                if p.exists() and p.stat().st_size < constants.MIN_CORRECT_CERT_SIZE:
                    logger.error(f'Corrupted file at: {p}')
                    # TODO: Delete


class CCDataset(Dataset, ComplexSerializableType):
    def __init__(self, certs: Dict[str, 'CommonCriteriaCert'], root_dir: Path, name: str = 'dataset name',
                 description: str = 'dataset_description'):
        super().__init__(certs, root_dir, name, description)

    @property
    def web_dir(self) -> Path:
        return self.root_dir / 'web'

    @property
    def certs_dir(self) -> Path:
        return self.root_dir / 'certs'

    @property
    def reports_dir(self) -> Path:
        return self.certs_dir / 'reports'

    @property
    def reports_pdf_dir(self) -> Path:
        return self.reports_dir / 'pdf'

    @property
    def reports_txt_dir(self) -> Path:
        return self.reports_dir / 'txt'

    @property
    def targets_dir(self) -> Path:
        return self.certs_dir / 'targets'

    @property
    def targets_pdf_dir(self) -> Path:
        return self.targets_dir / 'pdf'

    @property
    def targets_txt_dir(self) -> Path:
        return self.targets_dir / 'txt'

    @property
    def report_pdf_paths(self) -> Dict[str, Path]:
        return {x: self.reports_pdf_dir / (self[x].dgst + '.pdf') for x in self.certs}

    @property
    def report_txt_paths(self) -> Dict[str, Path]:
        return {x: self.reports_txt_dir / (self[x].dgst + '.txt') for x in self.certs}

    @property
    def target_pdf_paths(self) -> Dict[str, Path]:
        return {x: self.targets_pdf_dir / (self[x].dgst + '.pdf') for x in self.certs}

    @property
    def target_txt_paths(self) -> Dict[str, Path]:
        return {x: self.targets_txt_dir / (self[x].dgst + '.txt') for x in self.certs}

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

    def _merge_certs(self, certs: Dict[str, 'CommonCriteriaCert']):
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
        logger.info(
            f'Added {len(will_be_added)} new and merged further {n_merged} certificates to the dataset.')

    def get_certs_from_web(self, to_download=True, keep_metadata: bool = True, get_active=True, get_archived=True):
        """
        Downloads all metadata about certificates from CSV and HTML sources
        """
        self.web_dir.mkdir(parents=True, exist_ok=True)

        html_items = [(x, self.web_dir / y)
                      for y, x in self.html_products.items()]
        csv_items = [(x, self.web_dir / y)
                     for y, x in self.csv_products.items()]

        if not get_active:
            html_items = [x for x in html_items if 'active' not in str(x[1])]
            csv_items = [x for x in csv_items if 'active' not in str(x[1])]

        if not get_archived:
            html_items = [x for x in html_items if 'archived' not in str(x[1])]
            csv_items = [x for x in csv_items if 'archived' not in str(x[1])]

        html_urls, html_paths = [x[0] for x in html_items], [x[1] for x in html_items]
        csv_urls, csv_paths = [x[0] for x in csv_items], [x[1] for x in csv_items]

        if to_download is True:
            logger.info('Downloading required csv and html files.')
            self._download_parallel(html_urls, html_paths)
            self._download_parallel(csv_urls, csv_paths)

        logger.info('Adding CSV certificates to CommonCriteria dataset.')
        csv_certs = self._get_all_certs_from_csv(get_active, get_archived)
        self._merge_certs(csv_certs)

        # TODO: Someway along the way, 3 certificates get lost. Investigate and fix.
        logger.info('Adding HTML certificates to CommonCriteria dataset.')
        html_certs = self._get_all_certs_from_html(get_active, get_archived)
        self._merge_certs(html_certs)

        logger.info(f'The resulting dataset has {len(self)} certificates.')

        if not keep_metadata:
            shutil.rmtree(self.web_dir)

    def _get_all_certs_from_csv(self, get_active, get_archived) -> Dict[str, 'CommonCriteriaCert']:
        """
        Creates dictionary of new certificates from csv sources.
        """
        csv_sources = self.csv_products.keys()
        csv_sources = [
            x for x in csv_sources if 'active' not in x or get_active]
        csv_sources = [
            x for x in csv_sources if 'archived' not in x or get_archived]

        new_certs = {}
        for file in csv_sources:
            partial_certs = self._parse_single_csv(self.web_dir / file)
            logger.info(
                f'Parsed {len(partial_certs)} certificates from: {file}')
            new_certs.update(partial_certs)
        return new_certs

    @staticmethod
    def _parse_single_csv(file: Path) -> Dict[str, 'CommonCriteriaCert']:
        """
        Using pandas, this parses a single CSV file.
        """

        def _get_primary_key_str(row):
            prim_key = row['category'] + row['cert_name'] + row['report_link']
            return prim_key

        csv_header = ['category', 'cert_name', 'manufacturer', 'scheme', 'security_level', 'protection_profiles',
                      'not_valid_before', 'not_valid_after', 'report_link', 'st_link', 'maintainance_date',
                      'maintainance_title', 'maintainance_report_link', 'maintainance_st_link']

        df = pd.read_csv(file, engine='python', encoding='windows-1250')
        df = df.rename(
            columns={x: y for (x, y) in zip(list(df.columns), csv_header)})

        df['is_maintainance'] = ~df.maintainance_title.isnull()
        df = df.fillna(value='')

        df[['not_valid_before', 'not_valid_after', 'maintainance_date']] = df[
            ['not_valid_before', 'not_valid_after', 'maintainance_date']].apply(pd.to_datetime)

        df['dgst'] = df.apply(lambda row: helpers.get_first_16_bytes_sha256(
            _get_primary_key_str(row)), axis=1)
        df_base = df.loc[df.is_maintainance == False].copy()
        df_main = df.loc[df.is_maintainance == True].copy()

        n_all = len(df_base)
        n_deduplicated = len(df_base.drop_duplicates(subset=['dgst']))
        if (n_dup := n_all - n_deduplicated) > 0:
            logger.warning(
                f'The CSV {file} contains {n_dup} duplicates by the primary key.')

        df_base = df_base.drop_duplicates(subset=['dgst'])
        df_main = df_main.drop_duplicates()

        profiles = {x.dgst: set([CommonCriteriaCert.ProtectionProfile(y, None) for y in
                                 helpers.sanitize_protection_profiles(x.protection_profiles)]) for x in
                    df_base.itertuples()}
        updates = {x.dgst: set() for x in df_base.itertuples()}
        for x in df_main.itertuples():
            updates[x.dgst].add(CommonCriteriaCert.MaintainanceReport(x.maintainance_date.date(), x.maintainance_title,
                                                                      x.maintainance_report_link,
                                                                      x.maintainance_st_link))

        certs = {x.dgst: CommonCriteriaCert(x.category, x.cert_name, x.manufacturer, x.scheme, x.security_level,
                                            x.not_valid_before, x.not_valid_after, x.report_link, x.st_link, 'csv',
                                            None, None, profiles.get(x.dgst, None), updates.get(x.dgst, None)) for x in
                 df_base.itertuples()}
        return certs

    def _get_all_certs_from_html(self, get_active, get_archived) -> Dict[str, 'CommonCriteriaCert']:
        """
        Prepares dictionary of certificates from all html files.
        """
        html_sources = self.html_products.keys()
        html_sources = [
            x for x in html_sources if 'active' not in x or get_active]
        html_sources = [
            x for x in html_sources if 'archived' not in x or get_archived]

        new_certs = {}
        for file in html_sources:
            partial_certs = self._parse_single_html(self.web_dir / file)
            logger.info(
                f'Parsed {len(partial_certs)} certificates from: {file}')
            new_certs.update(partial_certs)
        return new_certs

    @staticmethod
    def _parse_single_html(file: Path) -> Dict[str, 'CommonCriteriaCert']:
        """
        Prepares a dictionary of certificates from a single html file.
        """

        def _get_timestamp_from_footer(footer):
            locale.setlocale(locale.LC_ALL, 'en_US')
            footer_text = list(footer.stripped_strings)[0]
            date_string = footer_text.split(',')[1:3]
            time_string = footer_text.split(',')[3].split(' at ')[1]
            formatted_datetime = date_string[0] + \
                date_string[1] + ' ' + time_string
            return datetime.strptime(formatted_datetime, ' %B %d %Y %I:%M %p')

        def _parse_table(soup: BeautifulSoup, table_id: str, category_string: str) -> Dict[str, 'CommonCriteriaCert']:
            tables = soup.find_all('table', id=table_id)
            assert len(tables) <= 1

            if not tables:
                return {}

            table = tables[0]
            rows = list(table.find_all('tr'))
            header, footer, body = rows[0], rows[1], rows[2:]

            # TODO: It's possible to obtain timestamp of the moment when the list was generated. It's identical for each table and should thus only be obtained once. Not necessarily in each table
            # timestamp = _get_timestamp_from_footer(footer)

            # TODO: Do we have use for number of expected certs? We get rid of duplicites, so no use for assert expected == actual
            # caption_str = str(table.findAll('caption'))
            # n_expected_certs = int(caption_str.split(category_string + ' – ')[1].split(' Certified Products')[0])
            table_certs = {x.dgst: x for x in [
                CommonCriteriaCert.from_html_row(row, category_string) for row in body]}

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

        with file.open('r') as handle:
            soup = BeautifulSoup(handle, 'html.parser')

        certs = {}
        for key, val in cat_dict.items():
            certs.update(_parse_table(soup, key, val))

        return certs

    def _download_reports(self):
        self.reports_pdf_dir.mkdir(parents=True, exist_ok=True)
        reports_urls = [x.report_link for x in self]
        self._download_parallel(reports_urls, self.report_pdf_paths.values(), prune_corrupted=True)

    def _download_targets(self):
        self.targets_pdf_dir.mkdir(parents=True, exist_ok=True)
        target_urls = [x.st_link for x in self]
        self._download_parallel(target_urls, self.target_pdf_paths.values(), prune_corrupted=True)

    def download_all_pdfs(self):
        logger.info('Downloading CC certificate reports')
        self._download_reports()

        logger.info('Downloading CC security targets')
        self._download_targets()

    def _convert_reports_to_txt(self):
        self.reports_txt_dir.mkdir(parents=True, exist_ok=True)
        # TODO: Get rid of the list() invocation here.
        self._convert_pdfs_to_txt(list(self.report_pdf_paths.values()), list(self.report_txt_paths.values()))

    def _convert_targets_to_txt(self):
        self.targets_txt_dir.mkdir(parents=True, exist_ok=True)
        # TODO: Get rid of the list() invocation here.
        self._convert_pdfs_to_txt(list(self.target_pdf_paths.values()), list(self.target_txt_paths.values()))

    def convert_all_pdfs(self):
        logger.info('Converting CC certificate reports to .txt')
        self._convert_reports_to_txt()

        logger.info('Converting CC security targets to .txt')
        self._convert_targets_to_txt()


class FIPSDataset(Dataset, ComplexSerializableType):
    FIPS_BASE_URL: ClassVar[str] = 'https://csrc.nist.gov'
    FIPS_MODULE_URL: ClassVar[
        str] = 'https://csrc.nist.gov/projects/cryptographic-module-validation-program/certificate/'

    def __init__(self, certs: dict, root_dir: Path, name: str = 'dataset name',
                 description: str = 'dataset_description'):
        super().__init__(certs, root_dir, name, description)
        self.keywords = {}
        self.new_files = 0

    @property
    def web_dir(self) -> Path:
        return self.root_dir / 'web'

    @property
    def results_dir(self) -> Path:
        return self.root_dir / 'results'

    @property
    def policies_dir(self) -> Path:
        return self.root_dir / 'security_policies'

    @property
    def fragments_dir(self) -> Path:
        return self.root_dir / 'fragments'

    def find_empty_pdfs(self) -> (List, List):
        missing = []
        not_available = []
        for i in self.certs:
            if not (self.policies_dir / f'{i}.pdf').exists():
                missing.append(i)
            elif os.path.getsize(self.policies_dir / f'{i}.pdf') < FIPS_NOT_AVAILABLE_CERT_SIZE:
                not_available.append(i)
        return missing, not_available

    def extract_keywords(self):
        self.fragments_dir.mkdir(parents=True, exist_ok=True)
        if self.new_files > 0 or not (self.root_dir / 'fips_full_keywords.json').exists():
            self.keywords = extract_certificates_keywords(
                self.policies_dir,
                self.fragments_dir, 'fips', fips_items=self.certs,
                should_censure_right_away=True)
        else:
            self.keywords = json.loads(
                open(self.root_dir / 'fips_full_keywords.json').read())

    def dump_keywords(self):
        with open(self.root_dir / "fips_full_keywords.json", 'w') as f:
            f.write(json.dumps(self.keywords, indent=4, sort_keys=True))

    # TODO figure out whether the name of this method shuold not be "get_certs", because we don't download every time

    def get_certs_from_web(self):
        def get_certificates_from_html(html_file: Path) -> None:
            logger.info(f'Getting certificate ids from {html_file}')
            html = BeautifulSoup(open(html_file).read(), 'html.parser')

            table = [x for x in html.find(
                id='searchResultsTable').tbody.contents if x != '\n']
            for entry in table:
                self.certs[entry.find('a').text] = {}

        logger.info("Downloading required html files")

        self.web_dir.mkdir(parents=True, exist_ok=True)
        self.policies_dir.mkdir(exist_ok=True)

        # Download files containing all available module certs (always)
        html_files = ['fips_modules_active.html',
                      'fips_modules_historical.html', 'fips_modules_revoked.html']
        helpers.download_file(
            "https://csrc.nist.gov/projects/cryptographic-module-validation-program/validated-modules/search?SearchMode=Advanced&CertificateStatus=Active&ValidationYear=0",
            self.web_dir / "fips_modules_active.html")
        helpers.download_file(
            "https://csrc.nist.gov/projects/cryptographic-module-validation-program/validated-modules/search?SearchMode=Advanced&CertificateStatus=Historical&ValidationYear=0",
            self.web_dir / "fips_modules_historical.html")
        helpers.download_file(
            "https://csrc.nist.gov/projects/cryptographic-module-validation-program/validated-modules/search?SearchMode=Advanced&CertificateStatus=Revoked&ValidationYear=0",
            self.web_dir / "fips_modules_revoked.html")

        # Parse those files and get list of currently processable files (always)
        for f in html_files:
            get_certificates_from_html(self.web_dir / f)

        logger.info('Downloading certficate html and security policies')
        html_items = [
            (f"https://csrc.nist.gov/projects/cryptographic-module-validation-program/certificate/{cert_id}",
             self.web_dir / f"{cert_id}.html") for cert_id in list(self.certs.keys()) if
            not (self.web_dir / f'{cert_id}.html').exists()]
        sp_items = [(
            f"https://csrc.nist.gov/CSRC/media/projects/cryptographic-module-validation-program/documents/security-policies/140sp{cert_id}.pdf",
            self.policies_dir / f"{cert_id}.pdf") for cert_id in list(self.certs.keys()) if
            not (self.policies_dir / f'{cert_id}.pdf').exists()]

        _, self.new_files = helpers.download_parallel(
            html_items + sp_items, 8), len(html_items) + len(sp_items)

        logger.info(f"{self.new_files} needed to be downloaded")

        if self.new_files > 0 or not (self.root_dir / 'fips_full_dataset.json').exists():
            # if False:
            for cert in self.certs:
                self.certs[cert] = FIPSCertificate.html_from_file(
                    self.web_dir / f'{cert}.html')
        else:
            logger.info("Certs loaded from previous scanning")
            dataset = json.loads(open(self.root_dir / 'fips_full_dataset.json').read(),
                                 cls=import_module('sec_certs.serialization').CustomJSONDecoder)
            self.certs = dataset.certs

    def extract_certs_from_tables(self) -> List[Path]:
        """
        Function that extracts algorithm IDs from tables in security policies files.
        :return: list of files that couldn't have been decoded
        """

        list_of_files = search_files(self.policies_dir)
        not_decoded = []
        for cert_file in list_of_files:
            cert_file = Path(cert_file)

            if '.txt' not in cert_file.suffixes:
                continue

            stem_name = Path(cert_file.stem).stem

            if self.certs[stem_name].tables_done:
                continue

            with open(cert_file, 'r') as f:
                tables = find_tables(f.read(), cert_file)

            # If we find any tables with page numbers, we process them
            if tables:
                lst = []
                try:
                    data = read_pdf(cert_file.with_suffix(''),
                                    pages=tables, silent=True)
                except Exception:
                    try:
                        repair_pdf(cert_file.with_suffix(''))
                        data = read_pdf(cert_file.with_suffix(
                            ''), pages=tables, silent=True)

                    except Exception:
                        not_decoded.append(cert_file)
                        continue

                # find columns with cert numbers
                for df in data:
                    for col in range(len(df.columns)):
                        if 'cert' in df.columns[col].lower() or 'algo' in df.columns[col].lower():
                            lst += FIPSCertificate.parse_algorithms(
                                df.iloc[:, col].to_string(index=False), True)

                    # Parse again if someone picks not so descriptive column names
                    lst += FIPSCertificate.parse_algorithms(
                        df.to_string(index=False))

                if lst:
                    self.certs[stem_name].algorithms += lst

            self.certs[stem_name].tables_done = True
        return not_decoded

    def remove_algorithms_from_extracted_data(self):
        """
        Function that removes all found certificate IDs that are matching any IDs labeled as algorithm IDs
        """
        for file_name in self.keywords:
            self.keywords[file_name]['file_status'] = True
            self.certs[file_name].file_status = True
            if self.certs[file_name].mentioned_certs:
                for item in self.certs[file_name].mentioned_certs:
                    self.keywords[file_name]['rules_cert_id'].update(item)

            for rule in self.keywords[file_name]['rules_cert_id']:
                to_pop = set()
                rr = re.compile(rule)
                for cert in self.keywords[file_name]['rules_cert_id'][rule]:
                    for alg in self.keywords[file_name]['rules_fips_algorithms']:
                        for found in self.keywords[file_name]['rules_fips_algorithms'][alg]:
                            if rr.search(found) and rr.search(cert) and rr.search(found).group('id') == rr.search(
                                    cert).group('id'):
                                to_pop.add(cert)
                for r in to_pop:
                    self.keywords[file_name]['rules_cert_id'][rule].pop(
                        r, None)

                self.keywords[file_name]['rules_cert_id'][rule].pop(
                    self.certs[file_name].cert_id, None)

    def validate_results(self):
        """
        Function that validates results and finds the final connection output
        """
        broken_files = set()
        for file_name in self.keywords:
            for rule in self.keywords[file_name]['rules_cert_id']:
                for cert in self.keywords[file_name]['rules_cert_id'][rule]:
                    cert_id = ''.join(filter(str.isdigit, cert))

                    if cert_id == '' or cert_id not in self.certs:
                        # TEST
                        # if cert_id == '' or int(cert_id) > 3730:
                        broken_files.add(file_name)
                        self.keywords[file_name]['file_status'] = False
                        self.certs[file_name].file_status = False
                        break
        if broken_files:
            logger.warning("CERTIFICATE FILES WITH WRONG CERTIFICATES PARSED")
            logger.warning(broken_files)
            logger.warning("... skipping these...")
            logger.warning(f"Total non-analyzable files:{len(broken_files)}")

        for file_name in self.keywords:
            self.certs[file_name].connections = []
            if not self.keywords[file_name]['file_status']:
                continue
            if self.keywords[file_name]['rules_cert_id'] == {}:
                continue
            for rule in self.keywords[file_name]['rules_cert_id']:
                for cert in self.keywords[file_name]['rules_cert_id'][rule]:
                    cert_id = ''.join(filter(str.isdigit, cert))
                    if cert_id not in self.certs[file_name].connections:
                        self.certs[file_name].connections.append(cert_id)

    def finalize_results(self):
        self.remove_algorithms_from_extracted_data()
        self.validate_results()
