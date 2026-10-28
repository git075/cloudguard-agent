"""
Terraform HCL Code Parser and Mutation Engine (Hardened for Security & Precision)
Parses .tf files into Python AST representations and generates safe HCL code modifications.
"""
import re
import logging
from typing import List, Dict, Any, Optional

from src.models.telemetry import TerraformResourceBlock, HCLMutationResult
from src.utils.security import sanitize_file_path

logger = logging.getLogger("cloudguard.hcl_parser")


class TerraformHCLParser:
    """
    Parser for Terraform HCL configuration files (.tf).
    Extracts resource declarations and safely updates attributes without altering comments.
    """

    def parse_hcl_content(self, file_path: str, content: str, base_dir: Optional[str] = None) -> List[TerraformResourceBlock]:
        """
        Parses HCL text content and returns a list of resource blocks.
        """
        clean_path = sanitize_file_path(file_path, base_dir=base_dir)
        blocks: List[TerraformResourceBlock] = []

        try:
            import hcl2
            parsed = hcl2.loads(content)
            resources = parsed.get("resource", [])
            for res_entry in resources:
                for res_type, res_dict in res_entry.items():
                    for res_name, res_attrs in res_dict.items():
                        blocks.append(
                            TerraformResourceBlock(
                                file_path=clean_path,
                                resource_type=res_type,
                                resource_name=res_name,
                                current_attributes=res_attrs if isinstance(res_attrs, dict) else {},
                            )
                        )
        except Exception as e:
            logger.info("Using AST regex parser fallback for %s: %s", clean_path, e)
            blocks = self._regex_fallback_parse(clean_path, content)

        return blocks

    def mutate_instance_spec(
        self,
        file_path: str,
        content: str,
        resource_type: str,
        resource_name: str,
        attribute_name: str,
        new_value: str,
        base_dir: Optional[str] = None,
    ) -> HCLMutationResult:
        """
        Replaces a specific resource attribute value (e.g. instance_class = "db.r5.2xlarge")
        with new_value (e.g. "db.r6g.xlarge") safely while ignoring comment lines.
        """
        clean_path = sanitize_file_path(file_path, base_dir=base_dir)

        if not new_value or not new_value.strip():
            raise ValueError("Replacement value cannot be empty")

        lines = content.splitlines(keepends=True)
        in_target_resource = False
        depth = 0
        target_header_re = re.compile(
            rf'resource\s+["\']?{re.escape(resource_type)}["\']?\s+["\']?{re.escape(resource_name)}["\']?\s*\{{'
        )
        attr_quoted_re = re.compile(rf'^(\s*{re.escape(attribute_name)}\s*=\s*")([^"]+)(".*)$')
        attr_unquoted_re = re.compile(
            rf'^(\s*{re.escape(attribute_name)}\s*=\s*)([^\s#/"\'][^\n\r#]*?)((\s*(?:#|//).*|\s*))$'
        )

        old_value = None
        updated_lines = []

        for line in lines:
            stripped = line.strip()
            # Ignore line comments when checking headers or attributes
            is_comment = stripped.startswith("#") or stripped.startswith("//")

            if not is_comment and not in_target_resource:
                if target_header_re.search(line):
                    in_target_resource = True
                    depth = line.count('{') - line.count('}')
                    if depth <= 0:
                        in_target_resource = False

            elif in_target_resource and not is_comment:
                depth += line.count('{') - line.count('}')
                if old_value is None:
                    # Check quoted attribute first (e.g. instance_type = "t3.medium")
                    match_quoted = attr_quoted_re.search(line)
                    if match_quoted:
                        old_value = match_quoted.group(2)
                        line = match_quoted.group(1) + new_value + match_quoted.group(3)
                        if not line.endswith("\n") and not line.endswith("\r"):
                            line += "\n"
                    else:
                        # Check unquoted attribute (e.g. instance_type = var.instance_type)
                        match_unquoted = attr_unquoted_re.search(line)
                        if match_unquoted:
                            old_value = match_unquoted.group(2).strip()
                            line = f'{match_unquoted.group(1)}"{new_value}"{match_unquoted.group(3)}'
                            if not line.endswith("\n") and not line.endswith("\r"):
                                line += "\n"
                if depth <= 0:
                    in_target_resource = False

            updated_lines.append(line)

        if old_value is None:
            raise ValueError(
                f"Could not locate active attribute '{attribute_name}' in resource '{resource_type}.{resource_name}'"
            )

        updated_code = "".join(updated_lines)

        return HCLMutationResult(
            file_path=clean_path,
            original_code=content,
            updated_code=updated_code,
            old_value=old_value,
            new_value=new_value,
            target_attribute=attribute_name,
        )

    def _regex_fallback_parse(self, file_path: str, content: str) -> List[TerraformResourceBlock]:
        """
        Regex-based fallback parser using brace depth matching for nested blocks.
        """
        blocks: List[TerraformResourceBlock] = []
        resource_pattern = re.compile(r'resource\s+"([^"]+)"\s+"([^"]+)"\s+{')

        for match in resource_pattern.finditer(content):
            res_type = match.group(1)
            res_name = match.group(2)
            start_pos = match.end()

            # Count brace depth to extract full block body
            depth = 1
            idx = start_pos
            while idx < len(content) and depth > 0:
                char = content[idx]
                if char == '{':
                    depth += 1
                elif char == '}':
                    depth -= 1
                idx += 1

            block_body = content[start_pos:idx-1] if depth == 0 else content[start_pos:]
            attrs: Dict[str, Any] = {}

            # Parse key = value assignments outside nested blocks
            for line in block_body.splitlines():
                line_stripped = line.strip()
                if line_stripped.startswith("#") or line_stripped.startswith("//"):
                    continue
                attr_match = re.match(r'^(\w+)\s*=\s*(.+)$', line_stripped)
                if attr_match:
                    key = attr_match.group(1)
                    val_str = attr_match.group(2).strip()

                    if val_str.startswith('"') and val_str.endswith('"'):
                        attrs[key] = val_str[1:-1]
                    elif val_str in ("true", "True"):
                        attrs[key] = True
                    elif val_str in ("false", "False"):
                        attrs[key] = False
                    elif val_str.isdigit():
                        attrs[key] = int(val_str)
                    else:
                        clean_val = re.split(r'\s+(?:#|//)', val_str)[0].strip()
                        attrs[key] = clean_val

            # Parse tags block if present
            tags_match = re.search(r'tags\s*=\s*{([^}]+)}', block_body)
            if tags_match:
                tags_dict = {}
                for tag_line in tags_match.group(1).splitlines():
                    t_match = re.match(r'^\s*(\w+)\s*=\s*"([^"]+)"', tag_line)
                    if t_match:
                        tags_dict[t_match.group(1)] = t_match.group(2)
                attrs["tags"] = tags_dict
            elif "tags" not in attrs:
                attrs["tags"] = {}

            blocks.append(
                TerraformResourceBlock(
                    file_path=file_path,
                    resource_type=res_type,
                    resource_name=res_name,
                    current_attributes=attrs,
                )
            )
        return blocks
