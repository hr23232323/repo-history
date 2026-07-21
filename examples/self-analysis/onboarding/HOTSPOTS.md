# Hotspots

Mechanically mined; no LLM involved.

## Most-changed files

| file | commits | churn |
| --- | ---: | ---: |
| `src/repo_history/cli.py` | 8 | 280 |
| `src/repo_history/git.py` | 7 | 373 |
| `tests/test_git.py` | 5 | 149 |
| `src/repo_history/build.py` | 4 | 371 |
| `README.md` | 4 | 322 |
| `tests/test_work.py` | 4 | 250 |
| `tests/test_analysis.py` | 4 | 212 |
| `src/repo_history/analysis/base.py` | 3 | 206 |
| `tests/test_build.py` | 3 | 162 |
| `src/repo_history/skill/SKILL.md` | 3 | 146 |
| `src/repo_history/memory.py` | 3 | 94 |
| `.gitignore` | 3 | 28 |
| `src/repo_history/analysis/mechanical.py` | 2 | 248 |
| `src/repo_history/work.py` | 2 | 193 |
| `src/repo_history/security.py` | 2 | 134 |
| `src/repo_history/models.py` | 2 | 64 |
| `pyproject.toml` | 2 | 43 |
| `docs/adding-a-method.md` | 1 | 116 |
| `tests/conftest.py` | 1 | 102 |
| `examples/self-analysis/DECISIONS.md` | 1 | 91 |
| `tests/test_memory.py` | 1 | 79 |
| `tests/test_state.py` | 1 | 76 |
| `src/repo_history/analysis/util.py` | 1 | 67 |
| `src/repo_history/mcp_server.py` | 1 | 60 |
| `src/repo_history/state.py` | 1 | 56 |

## Change coupling

Files that repeatedly change together.

| file A | file B | co-changes | confidence |
| --- | --- | ---: | ---: |
| `src/repo_history/git.py` | `tests/test_git.py` | 5 | 1.0 |
| `.gitignore` | `src/repo_history/cli.py` | 3 | 1.0 |
| `src/repo_history/build.py` | `tests/test_build.py` | 3 | 1.0 |
| `README.md` | `pyproject.toml` | 2 | 1.0 |
| `pyproject.toml` | `src/repo_history/cli.py` | 2 | 1.0 |
| `src/repo_history/analysis/mechanical.py` | `tests/test_analysis.py` | 2 | 1.0 |
| `src/repo_history/git.py` | `src/repo_history/work.py` | 2 | 1.0 |
| `src/repo_history/security.py` | `tests/test_work.py` | 2 | 1.0 |
| `src/repo_history/work.py` | `tests/test_work.py` | 2 | 1.0 |
| `src/repo_history/build.py` | `src/repo_history/models.py` | 2 | 1.0 |
| `src/repo_history/models.py` | `tests/test_build.py` | 2 | 1.0 |
| `src/repo_history/analysis/base.py` | `tests/test_analysis.py` | 2 | 0.667 |
| `src/repo_history/build.py` | `src/repo_history/memory.py` | 2 | 0.667 |
| `src/repo_history/analysis/base.py` | `src/repo_history/git.py` | 2 | 0.667 |
| `README.md` | `src/repo_history/cli.py` | 2 | 0.5 |
| `src/repo_history/git.py` | `tests/test_work.py` | 2 | 0.5 |
| `src/repo_history/build.py` | `src/repo_history/cli.py` | 2 | 0.5 |
| `src/repo_history/git.py` | `tests/test_analysis.py` | 2 | 0.5 |
| `src/repo_history/cli.py` | `src/repo_history/git.py` | 2 | 0.286 |
