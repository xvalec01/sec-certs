import os
from datetime import datetime
import locale
import logging
from typing import Dict, List, ClassVar, Collection, Union, Set, Tuple

import json
from abc import ABC, abstractmethod
from pathlib import Path
import shutil

from graphviz import Digraph
import requests
import pandas as pd
from bs4 import BeautifulSoup, Tag

import sec_certs.helpers as helpers
import sec_certs.constants as constants
import sec_certs.cert_processing as cert_processing
import sec_certs.files as files

from sec_certs.certificate import CommonCriteriaCert, Certificate, FIPSCertificate
from sec_certs.serialization import ComplexSerializableType, CustomJSONDecoder, CustomJSONEncoder

logger = logging.getLogger(__name__)


class Dataset(ABC):
    def __init__(self, certs: Dict[str, 'Certificate'], root_dir: Path, name: str = 'dataset name',
                 description: str = 'dataset_description'):
        self._root_dir = root_dir
        self.timestamp = datetime.now()
        self.sha256_digest = 'not implemented'
        self.name = name
        self.description = description
        self.certs = certs

    @property
    def root_dir(self):
        return self._root_dir

    @root_dir.setter
    def root_dir(self, new_dir: Union[str, Path]):
        if not (new_path := Path(new_dir)).exists():
            raise FileNotFoundError('Root directory for Dataset does not exist')
        self._root_dir = new_path

    def __iter__(self):
        yield from self.certs.values()

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
        if len(dset) != (claimed := dct['n_certs']):
            logger.error(
                f'The actual number of certs in dataset ({len(dset)}) does not match the claimed number ({claimed}).')
        return dset

    def to_json(self, output_path: Union[str, Path]):
        with Path(output_path).open('w') as handle:
            json.dump(self, handle, indent=4, cls=CustomJSONEncoder)

    @classmethod
    def from_json(cls, input_path: Union[str, Path]):
        input_path = Path(input_path)
        with input_path.open('r') as handle:
            dset = json.load(handle, cls=CustomJSONDecoder)
        dset.root_dir = input_path.parent.absolute()
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
    def _download_parallel(urls: Collection[str], paths: Collection[Path], prune_corrupted: bool = True):
        exit_codes = cert_processing.process_parallel(helpers.download_file,
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
    # TODO: Make properties propagate to changing internal state of related certificates

    @Dataset.root_dir.setter
    def root_dir(self, new_dir: Union[str, Path]):
        Dataset.root_dir.fset(self, new_dir)
        self.set_local_paths()

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

    @classmethod
    def from_json(cls, input_path: Union[str, Path]):
        dset = super().from_json(input_path)
        dset.set_local_paths()
        return dset

    def set_local_paths(self):
        for cert in self:
            cert.set_local_paths(self.reports_pdf_dir, self.targets_pdf_dir, self.reports_txt_dir, self.targets_txt_dir)

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

    def get_certs_from_web(self, to_download: bool = True, keep_metadata: bool = True, get_active: bool = True,
                           get_archived: bool = True):
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

        self.set_local_paths()

    def _get_all_certs_from_csv(self, get_active: bool, get_archived: bool) -> Dict[str, 'CommonCriteriaCert']:
        """
        Creates dictionary of new certificates from csv sources.
        """
        csv_sources = self.csv_products.keys()
        csv_sources = [x for x in csv_sources if 'active' not in x or get_active]
        csv_sources = [x for x in csv_sources if 'archived' not in x or get_archived]

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

        def _get_primary_key_str(row: Tag):
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
                                            None, None, profiles.get(x.dgst, None), updates.get(x.dgst, None), None) for
                 x in
                 df_base.itertuples()}
        return certs

    def _get_all_certs_from_html(self, get_active: bool, get_archived: bool) -> Dict[str, 'CommonCriteriaCert']:
        """
        Prepares dictionary of certificates from all html files.
        """
        html_sources = self.html_products.keys()
        if get_active is False:
            html_sources = filter(lambda x: 'active' not in x, html_sources)
        if get_archived is False:
            html_sources = filter(lambda x: 'archived' not in x, html_sources)

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

    def _download_reports(self, fresh=True):
        self.reports_pdf_dir.mkdir(parents=True, exist_ok=True)

        if fresh is True:
            certs_to_process = self.certs.values()
        else:
            certs_to_process = [x for x in self.certs.values() if not x.state.report_link_ok]

        cert_processing.process_parallel(CommonCriteriaCert.download_pdf_report, certs_to_process, constants.N_THREADS)

    def _download_targets(self, fresh=True):
        self.targets_pdf_dir.mkdir(parents=True, exist_ok=True)
        if fresh is True:
            certs_to_process = self.certs.values()
        else:
            certs_to_process = [x for x in self.certs.values() if not x.state.st_link_ok]
        cert_processing.process_parallel(CommonCriteriaCert.download_pdf_target, certs_to_process, constants.N_THREADS)

    def download_all_pdfs(self, fresh: bool = True):
        logger.info('Downloading CC certificate reports')
        self._download_reports(fresh)

        logger.info('Downloading CC security targets')
        self._download_targets(fresh)

        if fresh is True:
            # Attempt to re-download once if some files are missing
            if any(filter(lambda x: not x.state.report_link_ok, self.certs.values())):
                logger.info('Attempting to re-download failed report links.')
                self._download_reports(False)

            if any(filter(lambda x: not x.state.st_link_ok, self.certs.values())):
                logger.info('Attempting to re-download failed security target links.')
                self._download_targets(False)

    def _convert_reports_to_txt(self, fresh: bool = True):
        self.reports_txt_dir.mkdir(parents=True, exist_ok=True)

        if fresh is True:
            certs_to_process = self.certs.values()
        else:
            certs_to_process = [x for x in self.certs.values() if not x.state.report_convert_ok]
        cert_processing.process_parallel(CommonCriteriaCert.convert_report_pdf, certs_to_process, constants.N_THREADS)

    def _convert_targets_to_txt(self, fresh: bool = True):
        self.targets_txt_dir.mkdir(parents=True, exist_ok=True)

        if fresh is True:
            certs_to_process = self.certs.values()
        else:
            certs_to_process = [x for x in self.certs.values() if not x.state.st_convert_ok]
        cert_processing.process_parallel(CommonCriteriaCert.convert_target_pdf, certs_to_process, constants.N_THREADS)

    def convert_all_pdfs(self, fresh: bool = True):
        logger.info('Converting CC certificate reports to .txt')
        self._convert_reports_to_txt(fresh)

        logger.info('Converting CC security targets to .txt')
        self._convert_targets_to_txt(fresh)

        if fresh is True:
            # Attempt to re-convert once if some files failed
            if any(filter(lambda x: not x.state.report_convert_ok, self.certs.values())):
                logger.info('Attempting to re-convert failed report pdfs')
                self._convert_reports_to_txt(False)
            if any(filter(lambda x: not x.state.st_convert_ok, self.certs.values())):
                logger.info('Attempting to re-convert failed target pdfs')
                self._convert_targets_to_txt(False)


class FIPSDataset(Dataset, ComplexSerializableType):
    FIPS_BASE_URL: ClassVar[str] = 'https://csrc.nist.gov'
    FIPS_MODULE_URL: ClassVar[
        str] = 'https://csrc.nist.gov/projects/cryptographic-module-validation-program/certificate/'

    def __init__(self, certs: dict, root_dir: Path, name: str = 'dataset name',
                 description: str = 'dataset_description'):
        super().__init__(certs, root_dir, name, description)
        self.keywords = {}
        self.algorithms = None
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

    @property
    def algs_dir(self) -> Path:
        return self.web_dir / 'algorithms'

    def find_empty_pdfs(self) -> Tuple[List, List]:
        missing = []
        not_available = []
        for i in self.certs:
            if not (self.policies_dir / f'{i}.pdf').exists():
                missing.append(i)
            elif os.path.getsize(self.policies_dir / f'{i}.pdf') < constants.FIPS_NOT_AVAILABLE_CERT_SIZE:
                not_available.append(i)
        return missing, not_available

    def extract_keywords(self, redo=False):
        self.fragments_dir.mkdir(parents=True, exist_ok=True)
        if self.new_files > 0 or not (self.root_dir / 'fips_full_keywords.json').exists():

            keywords = cert_processing.process_parallel(FIPSCertificate.parse_cert_file,
                                                        [cert for cert in self.certs.values() if not cert.keywords or redo],
                                                        constants.N_THREADS,
                                                        use_threading=False)
            for keyword, cert in keywords:
                self.certs[cert.dgst].keywords = keyword
        else:
            self.keywords = json.loads(
                open(self.root_dir / 'fips_full_keywords.json').read())

    def dump_keywords(self):
        with open(self.root_dir / "fips_full_keywords.json", 'w') as f:
            f.write(json.dumps(self.keywords, indent=4, sort_keys=True))

    def download_all_pdfs(self):
        sp_paths, sp_urls = [], []
        self.policies_dir.mkdir(exist_ok=True)

        for cert_id in list(self.certs.keys()):
            if not (self.policies_dir / f'{cert_id}.pdf').exists():
                sp_urls.append(
                    f"https://csrc.nist.gov/CSRC/media/projects/cryptographic-module-validation-program/documents/security-policies/140sp{cert_id}.pdf")
                sp_paths.append(self.policies_dir / f"{cert_id}.pdf")
        logging.info(f"downloading {len(sp_urls)} module pdf files")
        cert_processing.process_parallel(FIPSCertificate.download_security_policy, list(zip(sp_urls, sp_paths)),
                                         constants.N_THREADS)
        self.new_files += len(sp_urls)

    def download_all_htmls(self):
        html_paths, html_urls = [], []

        self.web_dir.mkdir(exist_ok=True)
        for cert_id in list(self.certs.keys()):
            if not (self.web_dir / f'{cert_id}.html').exists():
                html_urls.append(
                    f"https://csrc.nist.gov/projects/cryptographic-module-validation-program/certificate/{cert_id}")
                html_paths.append(self.web_dir / f"{cert_id}.html")

        logging.info(f"downloading {len(html_urls)} module html files")
        cert_processing.process_parallel(FIPSCertificate.download_html_page, list(zip(html_urls, html_paths)),
                                         constants.N_THREADS)
        self.new_files += len(html_urls)

    def download_all_algs(self):
        algs_paths, algs_urls = [], []

        self.algs_dir.mkdir(exist_ok=True)
        for i in range(1, 502):
            if not (self.algs_dir / f'page{i}.html').exists():
                algs_urls.append(
                    f'https://csrc.nist.gov/projects/cryptographic-algorithm-validation-program/validation-search?searchMode=validation&page={i}')
                algs_paths.append(self.algs_dir / f"page{i}.html")

        logging.info(f"downloading {len(algs_urls)} algs html files")
        cert_processing.process_parallel(FIPSCertificate.download_html_page, list(zip(algs_urls, algs_paths)),
                                         constants.N_THREADS)
        self.new_files += len(algs_urls)

    def convert_all_pdfs(self):
        logger.info('Converting FIPS certificate reports to .txt')
        tuples = [
            (cert, self.policies_dir / f'{cert.cert_id}.pdf', self.policies_dir / f'{cert.cert_id}.pdf.txt')
            for cert in self.certs.values() if not cert.txt_state and (self.policies_dir / f'{cert.cert_id}.pdf').exists()
        ]
        cert_processing.process_parallel(FIPSCertificate.convert_pdf_file, tuples, constants.N_THREADS)

    def get_certs_from_web(self, redo=False):
        def download_html_pages():
            self.download_all_pdfs()
            self.download_all_htmls()
            self.download_all_algs()

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
        self.algs_dir.mkdir(exist_ok=True)

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
        download_html_pages()

        logger.info(f"{self.new_files} needed to be downloaded")

        if not (self.root_dir / 'fips_full_dataset.json').exists():
            for cert_id in self.certs:
                self.certs[cert_id] = FIPSCertificate.html_from_file(
                    self.web_dir / f'{cert_id}.html',
                    FIPSCertificate.State((self.policies_dir / cert_id).with_suffix('.pdf'),
                                          (self.web_dir / cert_id).with_suffix('.html'),
                                          (self.fragments_dir / cert_id).with_suffix('.txt')))
            return

        logger.info("Certs loaded from previous scanning")
        dataset = self.from_json(self.root_dir / 'fips_full_dataset.json')
        self.certs = dataset.certs
        if redo or self.new_files > 0:
            for cert_id, cert in self.certs.items():
                self.certs[cert_id] = FIPSCertificate.html_from_file(
                    self.web_dir / f'{cert_id}.html',
                    FIPSCertificate.State((self.policies_dir / cert_id).with_suffix('.pdf'),
                                          (self.web_dir / cert_id).with_suffix('.html'),
                                          (self.fragments_dir / cert_id).with_suffix('.txt')), cert)

    def extract_certs_from_tables(self) -> List[Path]:
        """
        Function that extracts algorithm IDs from tables in security policies files.
        :return: list of files that couldn't have been decoded
        """
        result = cert_processing.process_parallel(FIPSCertificate.analyze_tables,
                                                  [cert for cert in self.certs.values() if
                                                   not cert.tables_done and cert.txt_state],
                                                  constants.N_THREADS // 4,  # tabula already processes by parallel, so
                                                                            # it's counterproductive to use all threads
                                                  use_threading=False)

        not_decoded = list(map(lambda tup: tup[1].state.sp_path, filter(lambda tup: tup[0] is False, result)))
        for state, cert, algorithms in result:
            self.certs[cert.dgst].tables_done = state
            self.certs[cert.dgst].algorithms += algorithms

        return not_decoded

    def remove_algorithms_from_extracted_data(self):
        for cert in self.certs.values():
            cert.remove_algorithms()

    def unify_algorithms(self):
        for certificate in self.certs.values():
            new_algorithms = []
            for algorithm in certificate.algorithms:
                if isinstance(algorithm, dict):
                    new_algorithms.append(algorithm)
                else:
                    new_algorithms.append({'Certificate': [algorithm]})
            certificate.algorithms = new_algorithms

    def validate_results(self):
        """
        Function that validates results and finds the final connection output
        """

        def validate_id(processed_cert: FIPSCertificate, cert_candidate: str) -> bool:
            # returns True if candidates should _not_ be matched
            def compare_certs(current_certificate: 'FIPSCertificate', other_id: str):
                cert_first = current_certificate.date_validation[0].year
                cert_last = current_certificate.date_validation[-1].year
                conn_first = self.certs[other_id].date_validation[0].year
                conn_last = self.certs[other_id].date_validation[-1].year

                return cert_first - conn_first > 5 and cert_last - conn_last > 5

            # "< 105" still needs to be used, because of some old certs being revalidated
            if cert_candidate.isdecimal() and (int(cert_candidate) < 105 or compare_certs(processed_cert, cert_candidate)):
                return False
            if cert_candidate not in self.algorithms.certs:
                return True

            for cert_alg in processed_cert.algorithms:
                for certificate in cert_alg['Certificate']:
                    curr_id = ''.join(filter(str.isdigit, certificate))
                    if curr_id == cert_candidate:
                        return False

            algs = self.algorithms.certs[cert_candidate]
            for current_alg in algs:
                if processed_cert.vendor[:3] in current_alg.vendor:
                    return False
            return True

        broken_files = set()
        for current_cert in self.certs.values():
            if not current_cert.txt_state:
                continue
            for rule in current_cert.keywords['rules_cert_id']:
                for cert in current_cert.keywords['rules_cert_id'][rule]:
                    cert_id = ''.join(filter(str.isdigit, cert))

                    if cert_id == '' or cert_id not in self.certs:
                        broken_files.add(current_cert.dgst)
                        current_cert.file_status = False
                        break

        if broken_files:
            logger.warning("CERTIFICATE FILES WITH WRONG CERTIFICATES PARSED")
            logger.warning(broken_files)
            logger.warning("... skipping these...")
            logger.warning(f"Total non-analyzable files:{len(broken_files)}")

        for current_cert in self.certs.values():
            current_cert.connections = []
            if not current_cert.file_status or not current_cert.keywords:
                continue
            if current_cert.keywords['rules_cert_id'] == {}:
                continue
            for rule in current_cert.keywords['rules_cert_id']:
                for cert in current_cert.keywords['rules_cert_id'][rule]:
                    cert_id = ''.join(filter(str.isdigit, cert))
                    if cert_id not in current_cert.connections and validate_id(current_cert, cert_id):
                        current_cert.connections.append(cert_id)

    def finalize_results(self):
        self.unify_algorithms()
        self.remove_algorithms_from_extracted_data()
        self.validate_results()

    def get_dot_graph(self, output_file_name: str):
        """
        Function that plots .dot graph of dependencies between certificates
        Certificates with at least one dependency are displayed in "{output_file_name}connections.pdf", remaining
        certificates are displayed in {output_file_name}single.pdf
        :param output_file_name: prefix to "connections", "connections.pdf", "single" and "single.pdf"
        """
        dot = Digraph(comment='Certificate ecosystem')
        single_dot = Digraph(comment='Modules with no dependencies')
        single_dot.attr('graph', label='Single nodes', labelloc='t', fontsize='30')
        single_dot.attr('node', style='filled')
        dot.attr('graph', label='Dependencies', labelloc='t', fontsize='30')
        dot.attr('node', style='filled')

        def found_interesting_cert(current_key):
            if self.certs[current_key].vendor == highlighted_vendor:
                dot.attr('node', color='red')
                if self.certs[current_key].status == 'Revoked':
                    dot.attr('node', color='grey32')
                if self.certs[current_key].status == 'Historical':
                    dot.attr('node', color='gold3')
            if self.certs[current_key].vendor == "SUSE, LLC":
                dot.attr('node', color='lightblue')

        def color_check(current_key):
            dot.attr('node', color='lightgreen')
            if self.certs[current_key].status == 'Revoked':
                dot.attr('node', color='lightgrey')
            if self.certs[current_key].status == 'Historical':
                dot.attr('node', color='gold')
            found_interesting_cert(current_key)
            dot.node(current_key, label=current_key + '\n' + self.certs[current_key].vendor +
                                        ('\n' + self.certs[current_key].module_name
                                         if self.certs[current_key].module_name else ''))

        keys = 0
        edges = 0

        highlighted_vendor = 'Red Hat®, Inc.'
        for key in self.certs:
            if key != 'Not found' and self.certs[key].file_status:
                if self.certs[key].connections:
                    color_check(key)
                    keys += 1
                else:
                    single_dot.attr('node', color='lightblue')
                    found_interesting_cert(key)
                    single_dot.node(key, label=key + '\n' + self.certs[key].vendor + (
                        '\n' + self.certs[key].module_name if self.certs[key].module_name else ''))

        for key in self.certs:
            if key != 'Not found' and self.certs[key].file_status:
                for conn in self.certs[key].connections:
                    color_check(conn)
                    dot.edge(key, conn)
                    edges += 1

        logging.info(f"rendering {keys} keys and {edges} edges")

        dot.render(str(output_file_name) + '_connections', view=True)
        single_dot.render(str(output_file_name) + '_single', view=True)

    def to_dict(self):
        return {'timestamp': self.timestamp, 'sha256_digest': self.sha256_digest,
                'name': self.name, 'description': self.description,
                'n_certs': len(self), 'certs': self.certs, 'algs': self.algorithms}

    @classmethod
    def from_dict(cls, dct: Dict):
        certs = dct['certs']
        dset = cls(certs, Path('./'), dct['name'], dct['description'])
        dset.algorithms = dct['algs']
        if len(dset) != (claimed := dct['n_certs']):
            logger.error(
                f'The actual number of certs in dataset ({len(dset)}) does not match the claimed number ({claimed}).')
        return dset

    def to_json(self, output_path: Union[str, Path]):
        with Path(output_path).open('w') as handle:
            json.dump(self, handle, indent=4, cls=CustomJSONEncoder)

    @classmethod
    def from_json(cls, input_path: Union[str, Path]):
        input_path = Path(input_path)
        with input_path.open('r') as handle:
            dset = json.load(handle, cls=CustomJSONDecoder)
        dset.root_dir = input_path.parent.absolute()
        return dset


class FIPSAlgorithmDataset(Dataset, ComplexSerializableType):

    def get_certs_from_web(self):
        pass

    def parse_html(self):
        def split_alg(alg_string):
            cert_type = alg_string.rstrip('0123456789')
            cert_id = alg_string[len(cert_type):]
            return cert_type.strip(), cert_id.strip()

        for f in files.search_files(self.root_dir):
            html_soup = BeautifulSoup(open(f).read(), 'html.parser')
            table = html_soup.find('table', class_='table table-condensed publications-table table-bordered')
            spans = table.find_all('span')
            for span in spans:
                elements = span.find_all('td')
                vendor, implementation = elements[0].text, elements[1].text
                elements_sliced = elements[2:]
                for i in range(0, len(elements_sliced), 2):
                    alg_type, alg_id = split_alg(elements_sliced[i].text.strip())
                    validation_date = elements_sliced[i + 1].text.strip()
                    fips_alg = FIPSCertificate.Algorithm(alg_id, vendor, implementation, alg_type, validation_date)
                    if alg_id not in self.certs:
                        self.certs[alg_id] = []
                    self.certs[alg_id].append(fips_alg)

    def convert_all_pdfs(self):
        raise NotImplementedError('Not meant to be implemented')

    def download_all_pdfs(self):
        raise NotImplementedError('Not meant to be implemented')

    def to_dict(self):
        return {"certs": self.certs}

    @classmethod
    def from_dict(cls, dct: Dict):
        certs = dct['certs']
        dset = cls(certs, Path('./'), 'algorithms', 'algorithms used in dataset')
        return dset

    def to_json(self, output_path: Union[str, Path]):
        with Path(output_path).open('w') as handle:
            json.dump(self, handle, indent=4, cls=CustomJSONEncoder)

    @classmethod
    def from_json(cls, input_path: Union[str, Path]):
        input_path = Path(input_path)
        with input_path.open('r') as handle:
            dset = json.load(handle, cls=CustomJSONDecoder)
        dset.root_dir = input_path.parent.absolute()
        return dset