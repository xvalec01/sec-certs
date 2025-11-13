# CLAUDE.md - AI Assistant Guide for sec-certs

This document provides comprehensive guidance for AI assistants working with the sec-certs codebase.

## Project Overview

**sec-certs** is a Python tool for scraping and analyzing security certificates from Common Criteria (CC) and FIPS 140-2/3 frameworks. It processes certification data from 20+ government portals worldwide, extracts metadata from PDFs, performs vulnerability analysis, and enables large-scale research on security certification practices.

**Key Features:**
- Automated scraping of certification data from official portals
- PDF processing with text extraction and OCR
- Machine learning-based reference extraction
- Vulnerability matching via CPE/CVE databases
- Transitive vulnerability analysis through certification chains
- Export to JSON, Pandas DataFrames, and visualizations

**Academic Project:** Three peer-reviewed publications accompany this research tool (see README.md).

## Repository Structure

```
sec-certs/
├── src/sec_certs/          # Main source code
│   ├── cli.py              # Command-line interface
│   ├── configuration.py    # Pydantic-based configuration
│   ├── constants.py        # URLs, thresholds, patterns
│   ├── cert_rules.py       # SAR/EAL definitions
│   ├── rules.yaml          # Regex patterns for cert IDs
│   ├── dataset/            # Dataset processing
│   │   ├── dataset.py      # Base Dataset class
│   │   ├── cc.py           # Common Criteria datasets
│   │   ├── fips.py         # FIPS 140 datasets
│   │   └── ...             # Auxiliary datasets (CPE, CVE, etc.)
│   ├── sample/             # Individual certificate objects
│   │   ├── certificate.py  # Base Certificate class
│   │   ├── cc.py           # CCCertificate
│   │   ├── fips.py         # FIPSCertificate
│   │   └── ...             # Related data structures
│   ├── model/              # ML models and transformers
│   │   ├── reference_finder.py    # Cross-reference extraction
│   │   ├── cpe_matching.py        # Vulnerability matching
│   │   ├── cc_matching.py         # Scheme matching
│   │   └── references_nlp/        # NLP-based models
│   ├── heuristics/         # Rule-based extraction
│   │   ├── cc.py           # CC metadata extraction
│   │   ├── fips.py         # FIPS metadata extraction
│   │   └── common.py       # Shared heuristics
│   ├── utils/              # Utility functions
│   │   ├── pdf.py          # PDF processing
│   │   ├── helpers.py      # General utilities
│   │   ├── nlp.py          # NLP utilities
│   │   └── ...             # More utilities
│   └── serialization/      # JSON/Pandas conversion
├── tests/                  # Test suite
│   ├── cc/                 # Common Criteria tests
│   ├── fips/               # FIPS tests
│   └── data/               # Test fixtures
├── notebooks/              # Jupyter notebooks
│   ├── examples/           # Example usage (Binder-compatible)
│   └── ...                 # Research notebooks
├── docs/                   # Sphinx documentation
├── requirements/           # Pinned dependencies
├── .github/workflows/      # CI/CD pipelines
├── pyproject.toml          # Project configuration
├── Dockerfile              # Docker image
├── README.md               # User documentation
└── CONTRIBUTING.md         # Contribution guidelines
```

## Key Entry Points

### 1. Command-Line Interface (CLI)

**Location:** `src/sec_certs/cli.py:108`

**Usage:**
```bash
sec-certs <framework> <actions> [options]
```

**Frameworks:**
- `cc` - Common Criteria
- `fips` - FIPS 140-2/3
- `pp` - Protection Profiles

**Processing Pipeline Actions:**
```bash
sec-certs cc build              # Scrape certificate metadata
sec-certs cc process-aux-dsets  # Process CVE/CPE/scheme data
sec-certs cc download           # Download PDFs
sec-certs cc convert            # Convert PDFs to text
sec-certs cc analyze            # Extract metadata and references
sec-certs cc all                # Run entire pipeline
```

**Common Options:**
- `-o, --output DIR` - Output directory (default: `./datasets/{framework}`)
- `-i, --input JSON` - Resume from existing dataset JSON
- `-c, --config YAML` - Custom configuration file
- `-q, --quiet` - Suppress progress output

### 2. Python API

**Location:** `src/sec_certs/dataset/__init__.py:1`

**Basic Usage:**
```python
from sec_certs.dataset import CCDataset, FIPSDataset

# Load pre-processed dataset from web
dset = CCDataset.from_web()

# Convert to Pandas DataFrame
df = dset.to_pandas()

# Access individual certificates
for cert in dset:
    print(cert.name, cert.heuristics.related_cves)

# Save/load JSON snapshots
dset.to_json('./snapshot.json')
dset = CCDataset.from_json('./snapshot.json')

# Filter certificates
vulnerable = [c for c in dset if c.heuristics.related_cves]
```

## Development Setup

### System Requirements

**Operating System:** Linux (Ubuntu/Debian recommended), macOS, or Windows (WSL)

**System Dependencies:**
```bash
# Ubuntu/Debian
sudo apt-get install -y \
    libpoppler-cpp-dev \
    libqpdf-dev \
    tesseract-ocr \
    default-jdk \
    build-essential \
    pkg-config \
    python3-dev

# macOS (Homebrew)
brew install poppler qpdf tesseract openjdk
```

### Python Environment

**Required:** Python 3.10, 3.11, or 3.12

**Installation:**
```bash
# Clone repository
git clone https://github.com/crocs-muni/sec-certs.git
cd sec-certs

# Install with pip-tools (reproducible environment)
pip install -U pip-tools
pip-sync requirements/all_requirements.txt

# OR install in development mode
pip install -e ".[dev,nlp]"

# Download spaCy model (required)
python -m spacy download en_core_web_sm

# Install pre-commit hooks
pre-commit install
```

### Docker Alternative

```bash
docker pull seccerts/sec-certs
docker run -it seccerts/sec-certs sec-certs cc --help
```

## Key Technologies

### Core Stack
- **Python 3.10+** - Modern Python with type hints
- **Pandas/NumPy** - Data manipulation
- **Requests/BeautifulSoup** - Web scraping
- **Click** - CLI framework
- **Pydantic** - Configuration validation

### PDF Processing
- **pdftotext** (Poppler) - Text extraction
- **PyPDF/pikepdf** - PDF manipulation
- **pytesseract/Pillow** - OCR for scanned PDFs
- **tabula-py** - Table extraction (requires Java)

### Machine Learning & NLP
- **scikit-learn** - ML algorithms
- **spaCy** - NLP (requires `en_core_web_sm` model)
- **sentence-transformers** - Embeddings (optional, `nlp` extra)
- **catboost/optuna** - ML training (optional, `nlp` extra)

### Development Tools
- **Ruff 0.7.4** - Fast linter and formatter
- **mypy 1.13.0** - Static type checking
- **pytest** - Testing framework
- **pre-commit** - Git hooks
- **Sphinx/myst-nb** - Documentation

## Configuration

### Configuration File

**Location:** Custom YAML file (loaded via CLI: `sec-certs cc all -c config.yaml`)

**Schema:** Defined in `src/sec_certs/configuration.py:1`

**Key Settings:**
```yaml
# Threading
n_threads: 4

# Matching thresholds
cpe_matching_threshold: 90.0
cc_matching_threshold: 95.0
fips_matching_threshold: 70.0

# Dataset URLs (for from_web() loading)
cc_latest_snapshot: "https://sec-certs.org/static/dataset.json"
fips_latest_snapshot: "https://sec-certs.org/static/fips/dataset.json"

# NVD API
nvd_api_key: "your-api-key"  # Optional, increases rate limits

# Proxy settings
cc_use_proxy: false
fips_use_proxy: false

# UI
enable_progress_bars: true
```

**Environment Variables:** Prefix with `SECCERTS_`, e.g., `SECCERTS_N_THREADS=8`

### Constants

**Location:** `src/sec_certs/constants.py:1`

Contains:
- URLs for 20+ CC certification schemes (Germany, France, Netherlands, US, Canada, etc.)
- FIPS endpoints (CMVP, IG docs, algorithm validation)
- Thresholds (file sizes, garbage detection)
- Common Criteria categories and abbreviations
- Regex patterns for validation

### Certificate ID Rules

**Location:** `src/sec_certs/rules.yaml:1`

Country-specific regex patterns for extracting certificate IDs from PDFs. Used by heuristics module.

**Example:**
```yaml
DE:  # Germany
  - pattern: "BSI-DSZ-CC-\\d{4}-[A-Z]{2}"
    example: "BSI-DSZ-CC-0123-MA"
FR:  # France
  - pattern: "ANSSI-CC-\\d{4}/\\d{2}"
    example: "ANSSI-CC-2021/42"
```

## Development Workflows

### Code Quality Assurance

**Pre-commit Checks:**
```bash
# Run all checks
pre-commit run --all-files

# Run specific tools
ruff check .            # Linting
ruff format --check .   # Format checking
ruff format .           # Apply formatting
mypy .                  # Type checking
```

**Ruff Configuration (`pyproject.toml:110-131`):**
- Line length: 120 characters
- Target: Python 3.10+
- Rules: isort, pycodestyle, pyflakes, mccabe, pyupgrade, pathlib
- Max complexity: 10

**Mypy Configuration (`pyproject.toml:145-148`):**
- NumPy plugin enabled
- Missing imports ignored (due to many external dependencies)

### Testing

**Location:** `tests/`

**Run Tests:**
```bash
# All tests
pytest tests

# Exclude slow tests (recommended during development)
pytest -m "not slow" tests

# Exclude remote tests (network-dependent)
pytest -m "not remote" tests

# With coverage
pytest --cov=sec_certs tests

# Specific test file
pytest tests/cc/test_cc_dataset.py
```

**Test Markers:**
- `@pytest.mark.slow` - Long-running tests (e.g., full pipeline)
- `@pytest.mark.remote` - Tests requiring internet access

**Test Structure:**
- Tests mirror source: `tests/cc/` corresponds to `src/sec_certs/dataset/cc.py`, etc.
- Fixtures in `conftest.py` (both root and framework-specific)
- Test data in `tests/data/` (sample PDFs, JSONs, etc.)

**CI:** Tests run on every push (Python 3.10, 3.11, 3.12) via GitHub Actions

### Version Management

**System:** `setuptools-scm` (automatic versioning from git tags)

- Version NOT tracked in git
- Auto-generated to `src/sec_certs/_version.py` during install
- Release process: Create GitHub release with version tag → auto-deploy to PyPI/DockerHub

**Current Version:**
```python
from sec_certs import __version__
print(__version__)  # e.g., "0.5.0"
```

### Release Process

1. Update dependencies: `pre-commit autoupdate`
2. Pin linter versions in `pyproject.toml`
3. Compile requirements: `cd requirements && ./compile.sh`
4. Commit changes: `git add . && git commit -m "chore: update dependencies"`
5. Create GitHub release with proper version tag (e.g., `v0.6.0`)
6. GitHub Actions automatically:
   - Publishes to PyPI
   - Builds and pushes Docker images (multi-arch: amd64, arm64)
   - Updates documentation at sec-certs.org/docs

## Important Conventions

### Code Style

**Naming:**
- `snake_case` - Variables, functions, modules
- `PascalCase` - Classes
- `CAPS_CASE` - Constants

**Imports:**
```python
from __future__ import annotations  # Enable forward references (Python 3.10+)

# Standard library
import json
from pathlib import Path

# Third-party
import pandas as pd
from pydantic import BaseModel

# Local
from sec_certs.dataset import CCDataset
```

**Type Hints:**
- Use throughout (enforced by mypy)
- Generic types: `Dataset[CertSubType]`, `list[str]` (not `List[str]`)
- Optional: `str | None` (not `Optional[str]`)

### Architectural Patterns

**1. Generic Base Classes**
- `Dataset[CertSubType]` - Generic dataset container
- `Certificate[T, H, P]` - Generic certificate with type-safe heuristics and PDF data

**2. State Machine for Processing**
- Dataset processing tracked via `DatasetInternalState` (src/sec_certs/dataset/dataset.py:40)
- State flags: `meta_sources_parsed`, `artifacts_downloaded`, `pdfs_converted`, `auxiliary_datasets_processed`, `certs_analyzed`
- CLI checks preconditions before each step

**3. Serialization**
- Base class: `ComplexSerializableType` (src/sec_certs/serialization/json.py:20)
- Custom `to_dict()` / `from_dict()` methods
- JSON schemas for validation (src/sec_certs/serialization/schemas/)

**4. Parallel Processing**
- Configurable via `n_threads` in configuration
- Utilities in `src/sec_certs/utils/parallel_processing.py:1`
- Used for batch PDF processing, heuristics extraction

**5. Lazy Loading**
- Datasets can load from JSON snapshots without re-scraping
- PDFs downloaded on-demand
- Auxiliary datasets cached locally

### Error Handling

**Logging:**
```python
import logging
logger = logging.getLogger(__name__)

logger.info("Processing certificate...")
logger.warning("Missing PDF for certificate XYZ")
logger.error("Failed to extract metadata", exc_info=True)
```

**CLI Exit Codes:**
- `0` - Success
- `1` - Failure (EXIT_CODE_NOK in src/sec_certs/cli.py)

**Progress Bars:**
- `tqdm` used throughout
- Can be disabled: `config.enable_progress_bars = False`

## Common Tasks for AI Assistants

### 1. Adding New Regex Patterns

**File:** `src/sec_certs/rules.yaml:1`

**Example:** Add support for a new country's certificate IDs:
```yaml
IT:  # Italy
  - pattern: "OCSI-CERT-\\d{4}-[A-Z]{3}"
    example: "OCSI-CERT-2023-ABC"
    comment: "Italian scheme certificates"
```

**Testing:**
```bash
pytest tests/cc/test_cc_certificate.py -k "test_cert_id_extraction"
```

### 2. Extending Heuristics

**Files:**
- `src/sec_certs/heuristics/cc.py:1` - Common Criteria
- `src/sec_certs/heuristics/fips.py:1` - FIPS 140

**Example:** Add extraction for a new field:
```python
# In src/sec_certs/heuristics/cc.py

@dataclass
class CCHeuristics(Heuristics):
    # Existing fields...
    new_field: str | None = None  # Add new field

def extract_new_field(cert: CCCertificate) -> str | None:
    """Extract new field from certificate text."""
    if not cert.state.txt_path or not cert.state.txt_path.exists():
        return None

    text = cert.state.txt_path.read_text(errors='ignore')
    # Add extraction logic
    match = re.search(r'New Field: (.+)', text)
    return match.group(1) if match else None

# In compute_heuristics() method:
def compute_heuristics(self, cert: CCCertificate) -> CCHeuristics:
    # Existing extractions...
    new_field = extract_new_field(cert)
    return CCHeuristics(..., new_field=new_field)
```

### 3. Adding New Analysis Features

**File:** `src/sec_certs/dataset/dataset.py:500` (analyze method)

**Example:** Add a custom analyzer:
```python
from sec_certs.model.matching import Matcher

class MyCustomMatcher(Matcher):
    def compute(self, dataset: Dataset) -> None:
        """Run custom matching logic."""
        for cert in dataset:
            # Custom analysis
            result = self.analyze_cert(cert)
            cert.heuristics.custom_result = result

# In Dataset.analyze():
def analyze(self, ..., run_custom_matcher: bool = False) -> None:
    if run_custom_matcher:
        matcher = MyCustomMatcher()
        matcher.compute(self)
```

### 4. Working with Datasets

**Loading:**
```python
from sec_certs.dataset import CCDataset

# From web (pre-processed)
dset = CCDataset.from_web()

# From local JSON
dset = CCDataset.from_json('./dataset.json')

# From scratch (scraping)
dset = CCDataset()
dset.build()  # Scrapes certificate metadata
```

**Filtering:**
```python
# Certificates with CVEs
vulnerable = [c for c in dset if c.heuristics.related_cves]

# By year
recent = [c for c in dset if c.year_from and c.year_from >= 2020]

# By category
smartcards = [c for c in dset if 'smart card' in c.category.lower()]
```

**Analysis:**
```python
# Convert to DataFrame for analysis
df = dset.to_pandas()

# Group by country
df.groupby('cert_lab').size().sort_values(ascending=False)

# Plot year distribution
df.year_from.value_counts().sort_index().plot.line()
```

### 5. Adding Tests

**Create test file:** `tests/cc/test_new_feature.py`

```python
import pytest
from sec_certs.dataset import CCDataset

def test_new_feature():
    """Test description."""
    dset = CCDataset()
    # Test logic
    assert dset is not None

@pytest.mark.slow
def test_full_pipeline():
    """Slow test for full processing."""
    dset = CCDataset()
    dset.build()
    assert len(dset) > 0
```

**Run:**
```bash
pytest tests/cc/test_new_feature.py -v
```

### 6. Debugging PDF Processing

**Check PDF extraction:**
```python
from sec_certs.utils.pdf import convert_pdf_to_text
from pathlib import Path

pdf_path = Path('./certificate.pdf')
txt_path = Path('./certificate.txt')

# Convert with fallback to OCR
convert_pdf_to_text(pdf_path, txt_path, use_ocr=True)

# Read extracted text
text = txt_path.read_text(errors='ignore')
print(text[:1000])  # First 1000 chars
```

**Common issues:**
- Missing Poppler: Install `libpoppler-cpp-dev`
- OCR not working: Install `tesseract-ocr`
- Java errors (tabula): Install `default-jdk`

### 7. Configuration Management

**Load custom config:**
```python
from sec_certs.configuration import config

# Load from YAML
config.load_from_yaml('./my_config.yaml')

# Access settings
print(config.n_threads)
print(config.cpe_matching_threshold)

# Override programmatically
config.n_threads = 8
config.enable_progress_bars = False
```

**From CLI:**
```bash
sec-certs cc all -c custom_config.yaml
```

### 8. Working with References

**Reference extraction (NLP-based):**
```python
from sec_certs.model.reference_finder import ReferenceFinder

# Initialize finder
finder = ReferenceFinder()

# Find references in dataset
finder.compute(dset)

# Access reference graph
for cert in dset:
    print(f"{cert.name}:")
    print(f"  Directly references: {cert.heuristics.direct_transitive_cves}")
    print(f"  All references: {cert.heuristics.indirectly_referenced_by}")
```

### 9. Vulnerability Matching

**CPE/CVE matching:**
```python
from sec_certs.model.cpe_matching import CPEClassifier

# Initialize classifier
classifier = CPEClassifier()

# Match vulnerabilities
classifier.compute(dset)

# Check results
for cert in dset:
    if cert.heuristics.related_cves:
        print(f"{cert.name}: {cert.heuristics.related_cves}")
```

## File Location Quick Reference

### Core Files
| Purpose | Path |
|---------|------|
| CLI entry point | `src/sec_certs/cli.py:108` |
| Configuration | `src/sec_certs/configuration.py:1` |
| Constants/URLs | `src/sec_certs/constants.py:1` |
| Regex rules | `src/sec_certs/rules.yaml:1` |
| SAR/EAL definitions | `src/sec_certs/cert_rules.py:1` |

### Dataset Classes
| Purpose | Path |
|---------|------|
| Base Dataset | `src/sec_certs/dataset/dataset.py:1` |
| CC Dataset | `src/sec_certs/dataset/cc.py:1` |
| FIPS Dataset | `src/sec_certs/dataset/fips.py:1` |
| CPE Dataset | `src/sec_certs/dataset/cpe.py:1` |
| CVE Dataset | `src/sec_certs/dataset/cve.py:1` |

### Certificate Classes
| Purpose | Path |
|---------|------|
| Base Certificate | `src/sec_certs/sample/certificate.py:1` |
| CC Certificate | `src/sec_certs/sample/cc.py:1` |
| FIPS Certificate | `src/sec_certs/sample/fips.py:1` |

### Models & Analysis
| Purpose | Path |
|---------|------|
| Reference finder | `src/sec_certs/model/reference_finder.py:1` |
| CPE matching | `src/sec_certs/model/cpe_matching.py:1` |
| CC scheme matching | `src/sec_certs/model/cc_matching.py:1` |
| Transitive CVEs | `src/sec_certs/model/transitive_vulnerability_finder.py:1` |

### Heuristics
| Purpose | Path |
|---------|------|
| CC heuristics | `src/sec_certs/heuristics/cc.py:1` |
| FIPS heuristics | `src/sec_certs/heuristics/fips.py:1` |
| Common heuristics | `src/sec_certs/heuristics/common.py:1` |

### Utilities
| Purpose | Path |
|---------|------|
| PDF processing | `src/sec_certs/utils/pdf.py:1` |
| General helpers | `src/sec_certs/utils/helpers.py:1` |
| NLP utilities | `src/sec_certs/utils/nlp.py:1` |
| Parallel processing | `src/sec_certs/utils/parallel_processing.py:1` |

## CI/CD Pipelines

**Location:** `.github/workflows/`

### Tests (`tests.yml`)
- **Trigger:** Every push, pull request
- **Matrix:** Python 3.10, 3.11, 3.12
- **Command:** `pytest --cov=sec_certs -m "not remote" tests`
- **Coverage:** Uploaded to Codecov (Python 3.10 only)

### Pre-commit (`pre-commit.yml`)
- **Trigger:** Every push, pull request
- **Checks:** Ruff (lint + format), mypy

### Release (`release.yml`)
- **Trigger:** GitHub release publication
- **Jobs:**
  - Build Python package → Publish to PyPI (trusted publisher)
  - Build Docker image (multi-arch) → Push to DockerHub

### Docs (`docs.yml`)
- **Trigger:** Push to main, releases, manual
- **Build:** Sphinx with MyST-NB
- **Deploy:** sec-certs.org/docs (main branch and tags only)

## Troubleshooting

### Common Issues

**1. Import errors for sec_certs modules**
```bash
# Install in editable mode
pip install -e .
```

**2. Missing spaCy model**
```bash
python -m spacy download en_core_web_sm
```

**3. PDF processing fails**
```bash
# Install system dependencies
sudo apt-get install libpoppler-cpp-dev tesseract-ocr

# Test PDF extraction
python -c "import pdftotext; print('OK')"
```

**4. Type checking errors with mypy**
- Check `pyproject.toml:145-148` for configuration
- Many external dependencies lack stubs (set `ignore_missing_imports = true`)

**5. Tests fail with "remote" marker**
```bash
# Exclude remote tests (CI default)
pytest -m "not remote" tests
```

**6. Docker build issues**
- Ensure sufficient memory (4GB+)
- Multi-stage build requires git context

### Getting Help

**Documentation:** https://sec-certs.org/docs
**Issues:** https://github.com/crocs-muni/sec-certs/issues
**Papers:** See README.md for academic publications

## Best Practices for AI Assistants

1. **Always run tests before committing:**
   ```bash
   pytest -m "not slow and not remote" tests
   ```

2. **Use pre-commit hooks:**
   ```bash
   pre-commit run --all-files
   ```

3. **Reference specific line numbers:**
   - Format: `file_path:line_number`
   - Example: "The CLI entry point is in `src/sec_certs/cli.py:108`"

4. **Check state before dataset operations:**
   - Datasets have internal state tracking processing stages
   - Use `dset.state` to check what's been completed

5. **Handle missing data gracefully:**
   - Not all certificates have PDFs
   - Text extraction may fail (scanned PDFs)
   - Use `if cert.state.txt_path and cert.state.txt_path.exists():`

6. **Preserve reproducibility:**
   - Use pinned requirements from `requirements/*.txt`
   - Document any configuration changes
   - Include seed values for ML experiments

7. **Consider performance:**
   - Processing full datasets is slow (hours)
   - Use `dset.to_json()` to save intermediate results
   - Leverage `n_threads` configuration for parallelization

8. **Respect data sources:**
   - Web scraping is rate-limited (built into scraper)
   - Use `from_web()` to load pre-processed data when possible
   - Don't overwhelm certification portals

9. **Document new features:**
   - Add docstrings (sphinx-oneline style)
   - Update relevant sections in docs/
   - Include example usage in notebooks/

10. **Follow the academic context:**
    - This is a research tool with published papers
    - Changes should maintain reproducibility of research results
    - Consider impact on existing analyses before breaking changes

## Additional Resources

- **Website:** https://sec-certs.org
- **Documentation:** https://sec-certs.org/docs
- **GitHub:** https://github.com/crocs-muni/sec-certs
- **PyPI:** https://pypi.org/project/sec-certs/
- **DockerHub:** https://hub.docker.com/r/seccerts/sec-certs/
- **Example Notebooks:** https://github.com/crocs-muni/sec-certs/tree/main/notebooks/examples
- **Research Group:** https://crocs.fi.muni.cz/

---

**Last Updated:** 2025-11-13
**Version:** Based on repository state at commit 6aef9e9
