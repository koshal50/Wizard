"""Constants used across the Wizard CLI.

Central registry of file extension mappings, known configuration files,
framework detection rules, ignore directories, and standard library modules.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# File Extension → Language Mapping
# ---------------------------------------------------------------------------
EXTENSION_LANGUAGE_MAP: dict[str, str] = {
    # Python
    ".py": "Python",
    ".pyw": "Python",
    ".pyi": "Python",
    ".pyx": "Python",
    # JavaScript
    ".js": "JavaScript",
    ".mjs": "JavaScript",
    ".cjs": "JavaScript",
    ".jsx": "JavaScript",
    # TypeScript
    ".ts": "TypeScript",
    ".tsx": "TypeScript",
    ".mts": "TypeScript",
    ".cts": "TypeScript",
    # Java
    ".java": "Java",
    # Kotlin
    ".kt": "Kotlin",
    ".kts": "Kotlin",
    # Go
    ".go": "Go",
    # Rust
    ".rs": "Rust",
    # C
    ".c": "C",
    ".h": "C",
    # C++
    ".cpp": "C++",
    ".cxx": "C++",
    ".cc": "C++",
    ".hpp": "C++",
    ".hxx": "C++",
    ".hh": "C++",
    # C#
    ".cs": "C#",
    # PHP
    ".php": "PHP",
    # Ruby
    ".rb": "Ruby",
    # Swift
    ".swift": "Swift",
    # Dart
    ".dart": "Dart",
    # Scala
    ".scala": "Scala",
    # R
    ".r": "R",
    ".R": "R",
    # Shell
    ".sh": "Shell",
    ".bash": "Shell",
    ".zsh": "Shell",
    ".fish": "Shell",
    # PowerShell
    ".ps1": "PowerShell",
    ".psm1": "PowerShell",
    # Lua
    ".lua": "Lua",
    # Perl
    ".pl": "Perl",
    ".pm": "Perl",
    # Elixir
    ".ex": "Elixir",
    ".exs": "Elixir",
    # Haskell
    ".hs": "Haskell",
    # Clojure
    ".clj": "Clojure",
    ".cljs": "Clojure",
    ".cljc": "Clojure",
    # SQL
    ".sql": "SQL",
    # HTML
    ".html": "HTML",
    ".htm": "HTML",
    # CSS
    ".css": "CSS",
    ".scss": "SCSS",
    ".sass": "SASS",
    ".less": "LESS",
    # Markup / Config (tracked but not counted as "source")
    ".json": "JSON",
    ".yaml": "YAML",
    ".yml": "YAML",
    ".toml": "TOML",
    ".xml": "XML",
    ".md": "Markdown",
    ".rst": "reStructuredText",
    ".txt": "Text",
}

# Languages considered "source code" (vs. config/markup)
SOURCE_LANGUAGES: set[str] = {
    "Python", "JavaScript", "TypeScript", "Java", "Kotlin", "Go", "Rust",
    "C", "C++", "C#", "PHP", "Ruby", "Swift", "Dart", "Scala", "R",
    "Shell", "PowerShell", "Lua", "Perl", "Elixir", "Haskell", "Clojure",
    "SQL",
}

# ---------------------------------------------------------------------------
# Directories to Ignore During Scanning
# ---------------------------------------------------------------------------
IGNORE_DIRS: set[str] = {
    # Version control
    ".git", ".svn", ".hg",
    # Python
    "__pycache__", ".mypy_cache", ".pytest_cache", ".ruff_cache",
    "venv", ".venv", "env", ".env",
    ".tox", ".nox",
    "*.egg-info",
    # Node.js
    "node_modules", ".next", ".nuxt",
    # Build outputs
    "dist", "build", "out", "target",
    ".build", "_build",
    # IDE / Editor
    ".idea", ".vscode", ".vs",
    # OS
    ".DS_Store", "Thumbs.db",
    # Coverage / docs build
    "htmlcov", "coverage",
    ".coverage",
    "site-packages",
}

# ---------------------------------------------------------------------------
# Known Configuration Files (name → category)
# ---------------------------------------------------------------------------
CONFIG_FILES: dict[str, str] = {
    # Documentation
    "README.md": "Documentation",
    "README.rst": "Documentation",
    "README.txt": "Documentation",
    "README": "Documentation",
    "CHANGELOG.md": "Documentation",
    "CHANGELOG.rst": "Documentation",
    "CHANGES.md": "Documentation",
    "HISTORY.md": "Documentation",
    # License
    "LICENSE": "License",
    "LICENSE.md": "License",
    "LICENSE.txt": "License",
    "COPYING": "License",
    # Community
    "CONTRIBUTING.md": "Community",
    "CONTRIBUTING.rst": "Community",
    "CODE_OF_CONDUCT.md": "Community",
    "SECURITY.md": "Community",
    # Git
    ".gitignore": "Git",
    ".gitattributes": "Git",
    ".gitmodules": "Git",
    # Python packaging
    "pyproject.toml": "Python Packaging",
    "setup.py": "Python Packaging",
    "setup.cfg": "Python Packaging",
    "MANIFEST.in": "Python Packaging",
    "requirements.txt": "Python Dependencies",
    "requirements.in": "Python Dependencies",
    "Pipfile": "Python Dependencies",
    "Pipfile.lock": "Python Dependencies",
    "poetry.lock": "Python Dependencies",
    "conda.yaml": "Python Dependencies",
    "environment.yml": "Python Dependencies",
    # Node.js
    "package.json": "Node.js",
    "package-lock.json": "Node.js",
    "yarn.lock": "Node.js",
    "pnpm-lock.yaml": "Node.js",
    ".npmrc": "Node.js",
    ".nvmrc": "Node.js",
    "tsconfig.json": "TypeScript",
    # Java / JVM
    "pom.xml": "Java/Maven",
    "build.gradle": "Java/Gradle",
    "build.gradle.kts": "Java/Gradle",
    "settings.gradle": "Java/Gradle",
    "settings.gradle.kts": "Java/Gradle",
    "gradlew": "Java/Gradle",
    # Rust
    "Cargo.toml": "Rust",
    "Cargo.lock": "Rust",
    # Go
    "go.mod": "Go",
    "go.sum": "Go",
    # Containers
    "Dockerfile": "Container",
    "docker-compose.yml": "Container",
    "docker-compose.yaml": "Container",
    ".dockerignore": "Container",
    "compose.yml": "Container",
    "compose.yaml": "Container",
    # CI/CD
    ".travis.yml": "CI/CD",
    "Jenkinsfile": "CI/CD",
    "azure-pipelines.yml": "CI/CD",
    "bitbucket-pipelines.yml": "CI/CD",
    ".circleci/config.yml": "CI/CD",
    # Build
    "Makefile": "Build",
    "CMakeLists.txt": "Build",
    "Rakefile": "Build",
    "Taskfile.yml": "Build",
    "justfile": "Build",
    # Linting / Formatting
    ".eslintrc.json": "Linting",
    ".eslintrc.js": "Linting",
    ".eslintrc.yml": "Linting",
    ".prettierrc": "Formatting",
    ".prettierrc.json": "Formatting",
    ".prettierrc.yml": "Formatting",
    ".editorconfig": "Formatting",
    ".flake8": "Linting",
    ".pylintrc": "Linting",
    "ruff.toml": "Linting",
    ".ruff.toml": "Linting",
    "mypy.ini": "Type Checking",
    ".mypy.ini": "Type Checking",
    # Environment
    ".env.example": "Environment",
    ".env.sample": "Environment",
    ".env.template": "Environment",
}

# CI/CD directory patterns (contain workflow files)
CI_CD_DIRS: dict[str, str] = {
    ".github/workflows": "GitHub Actions",
    ".gitlab-ci.yml": "GitLab CI",
    ".circleci": "CircleCI",
}

# ---------------------------------------------------------------------------
# Framework Detection Indicators
# ---------------------------------------------------------------------------
# Each entry: { "files": [...], "dependencies": [...], "patterns": [...] }
FRAMEWORK_INDICATORS: dict[str, dict] = {
    # Python Frameworks
    "Django": {
        "ecosystem": "Python",
        "files": ["manage.py"],
        "dir_patterns": ["*/settings.py", "*/wsgi.py", "*/asgi.py"],
        "dependencies": ["django"],
    },
    "Flask": {
        "ecosystem": "Python",
        "files": [],
        "dir_patterns": [],
        "dependencies": ["flask"],
    },
    "FastAPI": {
        "ecosystem": "Python",
        "files": [],
        "dir_patterns": [],
        "dependencies": ["fastapi"],
    },
    "Streamlit": {
        "ecosystem": "Python",
        "files": [".streamlit/config.toml"],
        "dir_patterns": [],
        "dependencies": ["streamlit"],
    },
    # JavaScript / TypeScript Frameworks
    "React": {
        "ecosystem": "JavaScript",
        "files": [],
        "dir_patterns": [],
        "dependencies": ["react"],
    },
    "Next.js": {
        "ecosystem": "JavaScript",
        "files": ["next.config.js", "next.config.mjs", "next.config.ts"],
        "dir_patterns": [],
        "dependencies": ["next"],
    },
    "Vue": {
        "ecosystem": "JavaScript",
        "files": ["vue.config.js"],
        "dir_patterns": [],
        "dependencies": ["vue"],
    },
    "Nuxt": {
        "ecosystem": "JavaScript",
        "files": ["nuxt.config.js", "nuxt.config.ts"],
        "dir_patterns": [],
        "dependencies": ["nuxt"],
    },
    "Angular": {
        "ecosystem": "JavaScript",
        "files": ["angular.json"],
        "dir_patterns": [],
        "dependencies": ["@angular/core"],
    },
    "Express": {
        "ecosystem": "JavaScript",
        "files": [],
        "dir_patterns": [],
        "dependencies": ["express"],
    },
    "Svelte": {
        "ecosystem": "JavaScript",
        "files": ["svelte.config.js"],
        "dir_patterns": [],
        "dependencies": ["svelte"],
    },
    # Java Frameworks
    "Spring Boot": {
        "ecosystem": "Java",
        "files": [],
        "dir_patterns": ["**/application.properties", "**/application.yml"],
        "dependencies": ["spring-boot", "org.springframework.boot"],
    },
    # Rust Frameworks
    "Actix Web": {
        "ecosystem": "Rust",
        "files": [],
        "dir_patterns": [],
        "dependencies": ["actix-web"],
    },
    "Rocket": {
        "ecosystem": "Rust",
        "files": ["Rocket.toml"],
        "dir_patterns": [],
        "dependencies": ["rocket"],
    },
}

# ---------------------------------------------------------------------------
# Package Manager Detection
# ---------------------------------------------------------------------------
PACKAGE_MANAGER_INDICATORS: dict[str, dict] = {
    "pip": {
        "ecosystem": "Python",
        "files": ["requirements.txt", "requirements.in"],
        "dir_patterns": ["requirements/*.txt"],
    },
    "Poetry": {
        "ecosystem": "Python",
        "files": ["poetry.lock"],
        "toml_sections": ["tool.poetry"],  # in pyproject.toml
    },
    "Pipenv": {
        "ecosystem": "Python",
        "files": ["Pipfile", "Pipfile.lock"],
    },
    "Conda": {
        "ecosystem": "Python",
        "files": ["environment.yml", "conda.yaml"],
    },
    "npm": {
        "ecosystem": "Node.js",
        "files": ["package-lock.json"],
    },
    "Yarn": {
        "ecosystem": "Node.js",
        "files": ["yarn.lock"],
    },
    "pnpm": {
        "ecosystem": "Node.js",
        "files": ["pnpm-lock.yaml"],
    },
    "Maven": {
        "ecosystem": "Java",
        "files": ["pom.xml"],
    },
    "Gradle": {
        "ecosystem": "Java",
        "files": ["build.gradle", "build.gradle.kts"],
    },
    "Cargo": {
        "ecosystem": "Rust",
        "files": ["Cargo.toml"],
    },
    "Go Modules": {
        "ecosystem": "Go",
        "files": ["go.mod"],
    },
}

# ---------------------------------------------------------------------------
# Python Standard Library Modules (common subset for heuristic filtering)
# ---------------------------------------------------------------------------
PYTHON_STDLIB_MODULES: set[str] = {
    "abc", "aifc", "argparse", "array", "ast", "asynchat", "asyncio",
    "asyncore", "atexit", "base64", "bdb", "binascii", "binhex",
    "bisect", "builtins", "bz2", "calendar", "cgi", "cgitb", "chunk",
    "cmath", "cmd", "code", "codecs", "codeop", "collections",
    "colorsys", "compileall", "concurrent", "configparser", "contextlib",
    "contextvars", "copy", "copyreg", "cProfile", "crypt", "csv",
    "ctypes", "curses", "dataclasses", "datetime", "dbm", "decimal",
    "difflib", "dis", "distutils", "doctest", "email", "encodings",
    "enum", "errno", "faulthandler", "fcntl", "filecmp", "fileinput",
    "fnmatch", "fractions", "ftplib", "functools", "gc", "getopt",
    "getpass", "gettext", "glob", "grp", "gzip", "hashlib", "heapq",
    "hmac", "html", "http", "idlelib", "imaplib", "imghdr", "imp",
    "importlib", "inspect", "io", "ipaddress", "itertools", "json",
    "keyword", "lib2to3", "linecache", "locale", "logging", "lzma",
    "mailbox", "mailcap", "marshal", "math", "mimetypes", "mmap",
    "modulefinder", "multiprocessing", "netrc", "nis", "nntplib",
    "numbers", "operator", "optparse", "os", "ossaudiodev", "pathlib",
    "pdb", "pickle", "pickletools", "pipes", "pkgutil", "platform",
    "plistlib", "poplib", "posix", "posixpath", "pprint", "profile",
    "pstats", "pty", "pwd", "py_compile", "pyclbr", "pydoc",
    "queue", "quopri", "random", "re", "readline", "reprlib",
    "resource", "rlcompleter", "runpy", "sched", "secrets", "select",
    "selectors", "shelve", "shlex", "shutil", "signal", "site",
    "smtpd", "smtplib", "sndhdr", "socket", "socketserver", "spwd",
    "sqlite3", "ssl", "stat", "statistics", "string", "stringprep",
    "struct", "subprocess", "sunau", "symtable", "sys", "sysconfig",
    "syslog", "tabnanny", "tarfile", "telnetlib", "tempfile", "termios",
    "test", "textwrap", "threading", "time", "timeit", "tkinter",
    "token", "tokenize", "tomllib", "trace", "traceback", "tracemalloc",
    "tty", "turtle", "turtledemo", "types", "typing", "unicodedata",
    "unittest", "urllib", "uu", "uuid", "venv", "warnings", "wave",
    "weakref", "webbrowser", "winreg", "winsound", "wsgiref",
    "xdrlib", "xml", "xmlrpc", "zipapp", "zipfile", "zipimport", "zlib",
    # Common sub-packages people import
    "os.path", "collections.abc", "typing.extensions",
    "concurrent.futures", "email.mime", "http.client", "http.server",
    "urllib.parse", "urllib.request", "xml.etree", "xml.etree.ElementTree",
    "logging.handlers", "unittest.mock",
}

# ---------------------------------------------------------------------------
# Package Name → Import Name Mapping (common mismatches)
# ---------------------------------------------------------------------------
PACKAGE_IMPORT_MAP: dict[str, str] = {
    "pillow": "PIL",
    "scikit-learn": "sklearn",
    "opencv-python": "cv2",
    "opencv-python-headless": "cv2",
    "pyyaml": "yaml",
    "python-dateutil": "dateutil",
    "beautifulsoup4": "bs4",
    "python-dotenv": "dotenv",
    "pymysql": "pymysql",
    "psycopg2-binary": "psycopg2",
    "psycopg2": "psycopg2",
    "python-jose": "jose",
    "python-multipart": "multipart",
    "uvloop": "uvloop",
    "aiohttp": "aiohttp",
    "attrs": "attr",
    "msgpack-python": "msgpack",
    "protobuf": "google.protobuf",
    "grpcio": "grpc",
    "django-rest-framework": "rest_framework",
    "djangorestframework": "rest_framework",
}

# Reverse map for quick lookup
IMPORT_PACKAGE_MAP: dict[str, str] = {v: k for k, v in PACKAGE_IMPORT_MAP.items()}

# ---------------------------------------------------------------------------
# Documentation Extensions & Dirs
# ---------------------------------------------------------------------------
DOC_EXTENSIONS: set[str] = {".md", ".rst", ".txt", ".adoc"}
DOC_DIRS: set[str] = {"docs", "doc", "documentation", "wiki"}

# Template Extensions
TEMPLATE_EXTENSIONS: set[str] = {".html", ".jinja", ".jinja2", ".j2", ".hbs", ".ejs", ".pug", ".mustache"}
TEMPLATE_DIRS: set[str] = {"templates", "template", "views", "layouts"}

# Static Asset Extensions
STATIC_EXTENSIONS: set[str] = {
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico", ".webp", ".avif",
    ".woff", ".woff2", ".ttf", ".eot", ".otf",
    ".mp3", ".mp4", ".wav", ".ogg", ".webm",
    ".pdf",
}
STATIC_DIRS: set[str] = {"static", "assets", "public", "media", "images", "img", "fonts"}

# Test Dirs
TEST_DIRS: set[str] = {"test", "tests", "spec", "specs", "__tests__", "test_", "testing"}

# ---------------------------------------------------------------------------
# Repository Health Check Items
# ---------------------------------------------------------------------------
HEALTH_CHECKS: list[dict[str, str]] = [
    {"id": "readme", "name": "README present", "files": ["README.md", "README.rst", "README.txt", "README"]},
    {"id": "license", "name": "LICENSE present", "files": ["LICENSE", "LICENSE.md", "LICENSE.txt", "COPYING"]},
    {"id": "tests", "name": "Tests detected", "dirs": ["test", "tests", "spec", "specs", "__tests__"]},
    {"id": "docs", "name": "Documentation directory", "dirs": ["docs", "doc", "documentation"]},
    {"id": "ci_cd", "name": "CI/CD configuration", "files": [".travis.yml", "Jenkinsfile", "azure-pipelines.yml"], "dirs": [".github/workflows", ".circleci"]},
    {"id": "gitignore", "name": "Git ignore rules", "files": [".gitignore"]},
    {"id": "dep_manifest", "name": "Dependency manifest", "files": ["requirements.txt", "pyproject.toml", "package.json", "Cargo.toml", "pom.xml", "build.gradle", "go.mod"]},
    {"id": "contributing", "name": "Contribution guidelines", "files": ["CONTRIBUTING.md", "CONTRIBUTING.rst", "CONTRIBUTING"]},
    {"id": "code_of_conduct", "name": "Code of Conduct", "files": ["CODE_OF_CONDUCT.md", "CODE_OF_CONDUCT"]},
]

# ---------------------------------------------------------------------------
# Size Thresholds
# ---------------------------------------------------------------------------
LARGE_REPO_FILE_THRESHOLD = 10_000  # Files
LARGE_FILE_SIZE_THRESHOLD = 1_048_576  # 1 MB
VERY_LARGE_FILE_SIZE_THRESHOLD = 10_485_760  # 10 MB
