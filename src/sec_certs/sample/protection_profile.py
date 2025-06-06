from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any, Literal
from urllib.parse import unquote_plus, urlparse

import requests
from bs4 import Tag

from sec_certs import constants
from sec_certs.cert_rules import cc_rules
from sec_certs.configuration import config
from sec_certs.sample.certificate import Certificate, logger
from sec_certs.sample.certificate import Heuristics as BaseHeuristics
from sec_certs.sample.certificate import PdfData as BasePdfData
from sec_certs.sample.document_state import DocumentState
from sec_certs.serialization.json import ComplexSerializableType
from sec_certs.utils import cc_html_parsing, helpers, sanitization
from sec_certs.utils.extract import extract_keywords
from sec_certs.utils.pdf import convert_pdf_file, extract_pdf_metadata


class ProtectionProfile(
    Certificate["ProtectionProfile", "ProtectionProfile.Heuristics", "ProtectionProfile.PdfData"],
    ComplexSerializableType,
):
    @dataclass
    class Heuristics(BaseHeuristics, ComplexSerializableType):
        pass

    @dataclass
    class PdfData(BasePdfData, ComplexSerializableType):
        """
        Class to hold data related to PDF and txt files related to protection profiles.
        """

        report_metadata: dict[str, Any] | None = field(default=None)
        pp_metadata: dict[str, Any] | None = field(default=None)
        report_keywords: dict[str, Any] | None = field(default=None)
        pp_keywords: dict[str, Any] | None = field(default=None)
        report_filename: str | None = field(default=None)
        pp_filename: str | None = field(default=None)

        def __bool__(self) -> bool:
            return any(x is not None for x in vars(self))

    @dataclass(eq=True)
    class WebData(ComplexSerializableType):
        """
        Class to hold metadata about protection profiles found on commoncriteriaportal.org
        """

        category: str
        status: Literal["active", "archived"]
        is_collaborative: bool
        name: str
        version: str
        security_level: set[str]
        not_valid_before: date | None
        not_valid_after: date | None
        report_link: str | None
        pp_link: str | None
        scheme: str | None
        maintenances: list[tuple[Any]]

        @property
        def eal(self) -> str | None:
            return helpers.choose_lowest_eal(self.security_level)

        @classmethod
        def from_html_row(
            cls, row: Tag, status: Literal["active", "archived"], category: str, is_collaborative: bool
        ) -> ProtectionProfile.WebData:
            """
            Given bs4 tag of html row (fetched from cc portal), will build the object.
            """
            if is_collaborative:
                return cls._from_html_row_collaborative(row, category)
            return cls._from_html_row_classic_pp(row, status, category)

        @classmethod
        def _from_html_row_classic_pp(
            cls, row: Tag, status: Literal["active", "archived"], category: str
        ) -> ProtectionProfile.WebData:
            cells = list(row.find_all("td"))
            if status == "active" and len(cells) != 6:
                raise ValueError(
                    f"Unexpected number of <td> elements in PP html row. Expected: 6, actual: {len(cells)}"
                )
            if status == "archived" and len(cells) != 7:
                raise ValueError(
                    f"Unexpected number of <td> elements in PP html row. Expected: 6, actual: {len(cells)}"
                )

            pp_link = cls._html_row_get_link(cells[0])
            pp_name = cls._html_row_get_name(cells[0])
            if not sanitization.sanitize_cc_link(pp_link):
                raise ValueError(f"pp_link for PP {pp_name} is empty, cannot create PP record")

            mu_div = cc_html_parsing.html_row_get_maintenance_div(row)
            maintenance_updates = cc_html_parsing.parse_maintenance_div(mu_div) if mu_div else []
            if maintenance_updates:
                # Drop ST links, not filled in for PPs
                maintenance_updates = [x[:3] for x in maintenance_updates]

            return cls(
                category,
                status,
                False,
                pp_name,
                cls._html_row_get_version(cells[1]),
                cls._html_row_get_security_level(cells[2]),
                cls._html_row_get_date(cells[3]),
                None if status == "active" else cls._html_row_get_date(cells[4]),
                cls._html_row_get_link(cells[-1]),
                pp_link,
                cls._html_row_get_scheme(cells[-2]),
                maintenance_updates,
            )

        @classmethod
        def _from_html_row_collaborative(cls, row: Tag, category: str) -> ProtectionProfile.WebData:
            cells = list(row.find_all("td"))
            if len(cells) != 5:
                raise ValueError(
                    f"Unexpected number of <td> elements in collaborative PP html row. Expected: 5, actual: {len(cells)}"
                )

            pp_link = cls._html_row_get_collaborative_pp_link(cells[0])
            pp_name = cls._html_row_get_collaborative_name(cells[0])
            if not sanitization.sanitize_cc_link(pp_link):
                raise ValueError(f"pp_link for PP {pp_name} is empty, cannot create PP record")

            return cls(
                category,
                "active",
                True,
                pp_name,
                cls._html_row_get_version(cells[1]),
                cls._html_row_get_security_level(cells[2]),
                cls._html_row_get_date(cells[3]),
                None,
                cls._html_row_get_link(cells[-1]),
                pp_link,
                None,
                [],
            )

        @staticmethod
        def _html_row_get_date(cell: Tag) -> date | None:
            text = cell.get_text()
            extracted_date = datetime.strptime(text, "%Y-%m-%d").date() if text else None
            return extracted_date

        @staticmethod
        def _html_row_get_name(cell: Tag) -> str:
            return str(cell.find_all("a")[0].string)

        @staticmethod
        def _html_row_get_link(cell: Tag) -> str:
            return constants.CC_PORTAL_BASE_URL + str(cell.find_all("a")[0].get("href"))

        @staticmethod
        def _html_row_get_version(cell: Tag) -> str:
            return str(cell.text)

        @staticmethod
        def _html_row_get_security_level(cell: Tag) -> set[str]:
            return set(map(str, cell.stripped_strings))

        @staticmethod
        def _html_row_get_scheme(cell: Tag) -> str | None:
            schemes = list(map(str, cell.stripped_strings))
            return schemes[0] if schemes else None

        @staticmethod
        def _html_row_get_collaborative_name(cell: Tag) -> str:
            return list(map(str, cell.stripped_strings))[0]

        @staticmethod
        def _html_row_get_collaborative_pp_link(cell: Tag) -> str:
            return constants.CC_PORTAL_BASE_URL + str(
                [x for x in cell.find_all("a") if x.string == "Protection Profile"][0].get("href")
            )

    @dataclass
    class InternalState(ComplexSerializableType):
        """
        Class to hold internal state for each of the documents.
        """

        pp: DocumentState = field(default_factory=DocumentState)
        report: DocumentState = field(default_factory=DocumentState)

    def __init__(
        self,
        web_data: WebData,
        pdf_data: PdfData | None = None,
        heuristics: Heuristics | None = None,
        state: InternalState | None = None,
    ):
        super().__init__()
        self.web_data: ProtectionProfile.WebData = web_data
        self.pdf_data: ProtectionProfile.PdfData = pdf_data if pdf_data else ProtectionProfile.PdfData()
        self.heuristics: ProtectionProfile.Heuristics = heuristics if heuristics else ProtectionProfile.Heuristics()
        self.state: ProtectionProfile.InternalState = state if state else ProtectionProfile.InternalState()

    @property
    def dgst(self) -> str:
        """
        digest of thwe protection profile, formed as first 16 bytes of `category|name|version` fields from `WebData` object.
        """
        return helpers.get_first_16_bytes_sha256(
            "|".join([self.web_data.category, self.web_data.name, self.web_data.version])
        )

    def __str__(self) -> str:
        return f"PP: {self.web_data.name}, dgst: {self.dgst}"

    @property
    def label_studio_title(self) -> str:
        return self.web_data.name

    def merge(self, other: ProtectionProfile, other_source: str | None = None) -> None:
        raise ValueError("Merging of PPs not implemented.")

    def set_local_paths(
        self,
        report_pdf_dir: str | Path | None,
        pp_pdf_dir: str | Path | None,
        report_txt_dir: str | Path | None,
        pp_txt_dir: str | Path | None,
    ) -> None:
        """
        Adjusts local paths for various files.
        """
        if report_pdf_dir:
            self.state.report.pdf_path = Path(report_pdf_dir) / f"{self.dgst}.pdf"
        if pp_pdf_dir:
            self.state.pp.pdf_path = Path(pp_pdf_dir) / f"{self.dgst}.pdf"
        if report_txt_dir:
            self.state.report.txt_path = Path(report_txt_dir) / f"{self.dgst}.txt"
        if pp_txt_dir:
            self.state.pp.txt_path = Path(pp_txt_dir) / f"{self.dgst}.txt"

    @classmethod
    def from_html_row(
        cls, row: Tag, status: Literal["active", "archived"], category: str, is_collaborative: bool
    ) -> ProtectionProfile:
        """
        Builds a `ProtectionProfile` object from html row obtained from cc portal html source.
        """
        return cls(ProtectionProfile.WebData.from_html_row(row, status, category, is_collaborative))

    @staticmethod
    def download_pdf_report(cert: ProtectionProfile) -> ProtectionProfile:
        """
        Downloads pdf of certification report for the given protection profile.
        """
        exit_code: str | int | None
        if not cert.web_data.report_link:
            exit_code = "No link"
        else:
            exit_code = helpers.download_file(
                cert.web_data.report_link, cert.state.report.pdf_path, proxy=config.cc_use_proxy
            )
        if exit_code != requests.codes.ok:
            error_msg = f"failed to download report from {cert.web_data.report_link}, code: {exit_code}"
            logger.error(f"Cert dgst: {cert.dgst} " + error_msg)
            cert.state.report.download_ok = False
        else:
            cert.state.report.download_ok = True
            cert.state.report.pdf_hash = helpers.get_sha256_filepath(cert.state.report.pdf_path)
            cert.pdf_data.report_filename = unquote_plus(str(urlparse(cert.web_data.report_link).path).split("/")[-1])
        return cert

    @staticmethod
    def download_pdf_pp(cert: ProtectionProfile) -> ProtectionProfile:
        """
        Downloads actual pdf of the given protection profile.
        """
        exit_code: str | int | None
        if not cert.web_data.pp_link:
            exit_code = "No link"
        else:
            exit_code = helpers.download_file(cert.web_data.pp_link, cert.state.pp.pdf_path, proxy=config.cc_use_proxy)
        if exit_code != requests.codes.ok:
            error_msg = f"failed to download PP from {cert.web_data.pp_link}, code: {exit_code}"
            logger.error(f"Cert dgst: {cert.dgst} " + error_msg)
            cert.state.pp.download_ok = False
        else:
            cert.state.pp.download_ok = True
            cert.state.pp.pdf_hash = helpers.get_sha256_filepath(cert.state.pp.pdf_path)
            cert.pdf_data.pp_filename = unquote_plus(str(urlparse(cert.web_data.pp_link).path).split("/")[-1])
        return cert

    @staticmethod
    def convert_report_pdf(cert: ProtectionProfile) -> ProtectionProfile:
        """
        Converts certification reports from pdf to txt.
        """
        ocr_done, ok_result = convert_pdf_file(cert.state.report.pdf_path, cert.state.report.txt_path)
        cert.state.report.convert_garbage = ocr_done
        cert.state.report.convert_ok = ok_result
        if not ok_result:
            logger.error(f"Cert dgst: {cert.dgst} failed to convert report pdf to txt")
        else:
            cert.state.report.txt_hash = helpers.get_sha256_filepath(cert.state.report.txt_path)
        return cert

    @staticmethod
    def convert_pp_pdf(cert: ProtectionProfile) -> ProtectionProfile:
        """
        Converts the actual protection profile from pdf to txt.
        """
        ocr_done, ok_result = convert_pdf_file(cert.state.pp.pdf_path, cert.state.pp.txt_path)
        cert.state.pp.convert_garbage = ocr_done
        cert.state.pp.convert_ok = ok_result
        if not ok_result:
            logger.error(f"Cert dgst: {cert.dgst} failed to convert PP pdf to txt")
        else:
            cert.state.pp.txt_hash = helpers.get_sha256_filepath(cert.state.pp.txt_path)
        return cert

    @staticmethod
    def extract_report_pdf_metadata(cert: ProtectionProfile) -> ProtectionProfile:
        """
        Extracts various pdf metadata from the certification report.
        """
        try:
            cert.pdf_data.report_metadata = extract_pdf_metadata(cert.state.report.pdf_path)
            cert.state.report.extract_ok = True
        except ValueError:
            cert.state.report.extract_ok = False
        return cert

    @staticmethod
    def extract_pp_pdf_metadata(cert: ProtectionProfile) -> ProtectionProfile:
        """
        Extracts various pdf metadata from the actual protection profile.
        """
        try:
            cert.pdf_data.pp_metadata = extract_pdf_metadata(cert.state.pp.pdf_path)
            cert.state.pp.extract_ok = True
        except ValueError:
            cert.state.pp.extract_ok = False

        return cert

    @staticmethod
    def extract_report_pdf_keywords(cert: ProtectionProfile) -> ProtectionProfile:
        """
        Extracts keywords using regexes from the certification report.
        """
        report_keywords = extract_keywords(cert.state.report.txt_path, cc_rules)
        if report_keywords is None:
            cert.state.report.extract_ok = False
        else:
            cert.pdf_data.report_keywords = report_keywords
        return cert

    @staticmethod
    def extract_pp_pdf_keywords(cert: ProtectionProfile) -> ProtectionProfile:
        """
        Extracts keywords using regexes from the actual protection profile.
        """
        pp_keywords = extract_keywords(cert.state.pp.txt_path, cc_rules)
        if pp_keywords is None:
            cert.state.pp.extract_ok = False
        else:
            cert.pdf_data.pp_keywords = pp_keywords
        return cert
