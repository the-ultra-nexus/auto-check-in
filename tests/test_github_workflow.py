"""双向校验 .env.example 的 @ci 标记与 GitHub Actions 工作流 env 映射。

约定（见 .env.example 头部说明）：
- `VAR=  # @ci:secrets` / `# @ci:vars`：CI 必须透传，来源必须匹配。
- 未标记变量仅本地使用，不要求进 CI。

校验方向：
1. 标记了但工作流未映射（或来源不一致）→ 失败。
2. 工作流引用了 .env.example 未声明（或标记不一致）的变量 → 失败。
"""

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENV_EXAMPLE = ROOT / ".env.example"
WORKFLOW_DIR = ROOT / ".github" / "workflows"

_VAR_LINE = re.compile(r"^\s*([A-Z][A-Z0-9_]*)\s*=")
_MARKER = re.compile(r"#\s*@ci:(secrets|vars)\b")
# 兼容 CHECK_IN_SITES: ${{ inputs.sites || vars.CHECK_IN_SITES }}
_CI_REF = re.compile(
    r"\$\{\{\s*(?:inputs\.[A-Za-z0-9_]+\s*\|\|\s*)?(secrets|vars)\.([A-Z0-9_]+)\s*\}\}"
)


def parse_env_example(text: str) -> dict[str, str]:
    """返回 {变量名: 标记(secrets/vars)}，仅保留带 @ci 标记的声明。"""
    declared: dict[str, str] = {}
    for line in text.splitlines():
        match = _VAR_LINE.match(line)
        if not match:
            continue
        name = match.group(1)
        marker = _MARKER.search(line)
        if marker:
            declared[name] = marker.group(1)
    return declared


def parse_workflow_refs(text: str) -> dict[str, set[str]]:
    """返回工作流 env 中引用的 {变量名: {secrets, vars}}。"""
    refs: dict[str, set[str]] = {}
    for source, name in _CI_REF.findall(text):
        refs.setdefault(name, set()).add(source)
    return refs


def find_inconsistencies(env_example_text: str, workflow_texts: list[str]) -> list[str]:
    declared = parse_env_example(env_example_text)
    refs: dict[str, set[str]] = {}
    for text in workflow_texts:
        for name, sources in parse_workflow_refs(text).items():
            refs.setdefault(name, set()).update(sources)

    errors: list[str] = []
    for name, marker in sorted(declared.items()):
        sources = refs.get(name, set())
        if marker not in sources:
            errors.append(f"{name} 标记为 @ci:{marker} 但工作流未映射为 {marker}.{name}")
    for name, sources in sorted(refs.items()):
        if name not in declared:
            errors.append(
                f"工作流引用了 {sorted(sources)}.{name} 但 .env.example 未声明该变量"
            )
        elif sources != {declared[name]}:
            errors.append(
                f"{name} 工作流映射为 {sorted(sources)}，与 .env.example 标记 @ci:{declared[name]} 不一致"
            )
    return errors


ENV_OK = """\
SITE_CONFIGS=  # @ci:secrets
CHECK_IN_SITES=  # @ci:vars
CHECK_IN_SESSION_DIR=
"""

WORKFLOW_OK = """\
env:
  SITE_CONFIGS: ${{ secrets.SITE_CONFIGS }}
  CHECK_IN_SITES: ${{ inputs.sites || vars.CHECK_IN_SITES }}
"""


class EnvConsistencyTest(unittest.TestCase):
    def test_complete_mapping_ok(self) -> None:
        self.assertEqual(find_inconsistencies(ENV_OK, [WORKFLOW_OK]), [])

    def test_missing_marked_var_fails(self) -> None:
        workflow = "env:\n  SITE_CONFIGS: ${{ secrets.SITE_CONFIGS }}\n"
        errors = find_inconsistencies(ENV_OK, [workflow])
        self.assertTrue(any("CHECK_IN_SITES" in err for err in errors))

    def test_wrong_source_fails(self) -> None:
        workflow = "env:\n  SITE_CONFIGS: ${{ vars.SITE_CONFIGS }}\n  CHECK_IN_SITES: ${{ vars.CHECK_IN_SITES }}\n"
        errors = find_inconsistencies(ENV_OK, [workflow])
        self.assertTrue(any("SITE_CONFIGS" in err for err in errors))

    def test_undeclared_workflow_ref_fails(self) -> None:
        workflow = WORKFLOW_OK + "  MY_SECRET: ${{ secrets.MY_SECRET }}\n"
        errors = find_inconsistencies(ENV_OK, [workflow])
        self.assertTrue(any("MY_SECRET" in err for err in errors))

    def test_local_only_var_not_required(self) -> None:
        self.assertEqual(find_inconsistencies(ENV_OK, [WORKFLOW_OK]), [])

    def test_repo_env_matches_workflows(self) -> None:
        self.assertTrue(ENV_EXAMPLE.exists(), f"缺少 {ENV_EXAMPLE}")
        self.assertTrue(WORKFLOW_DIR.exists(), f"缺少 {WORKFLOW_DIR}")
        texts = [
            path.read_text()
            for path in sorted(WORKFLOW_DIR.glob("*.yml")) + sorted(WORKFLOW_DIR.glob("*.yaml"))
        ]
        self.assertEqual(find_inconsistencies(ENV_EXAMPLE.read_text(), texts), [])


if __name__ == "__main__":
    unittest.main()
