"""
Unit Tests for Terraform HCL Parser and Mutation Engine
"""
import unittest
from src.services.hcl_parser import TerraformHCLParser

SAMPLE_TF_CONTENT = """
resource "aws_db_instance" "production_db" {
  allocated_storage   = 100
  engine              = "postgres"
  instance_class      = "db.r5.2xlarge"
  skip_final_snapshot = true

  tags = {
    Environment = "production"
    Owner       = "devops"
  }
}
"""


class TestTerraformHCLParser(unittest.TestCase):

    def test_parse_hcl_content(self):
        parser = TerraformHCLParser()
        blocks = parser.parse_hcl_content("main.tf", SAMPLE_TF_CONTENT)

        self.assertEqual(len(blocks), 1)
        block = blocks[0]
        self.assertEqual(block.resource_type, "aws_db_instance")
        self.assertEqual(block.resource_name, "production_db")
        self.assertEqual(block.current_attributes.get("instance_class"), "db.r5.2xlarge")

    def test_mutate_instance_spec(self):
        parser = TerraformHCLParser()
        result = parser.mutate_instance_spec(
            file_path="main.tf",
            content=SAMPLE_TF_CONTENT,
            resource_type="aws_db_instance",
            resource_name="production_db",
            attribute_name="instance_class",
            new_value="db.r6g.xlarge",
        )

        self.assertEqual(result.old_value, "db.r5.2xlarge")
        self.assertEqual(result.new_value, "db.r6g.xlarge")
        self.assertIn('instance_class      = "db.r6g.xlarge"', result.updated_code)
        self.assertIn('skip_final_snapshot = true', result.updated_code)


    def test_mutate_instance_spec_with_long_comments(self):
        parser = TerraformHCLParser()
        content_with_comments = """# This is a very long comment header that alters character offset position significantly
# Another comment line describing the infrastructure setup
resource "aws_db_instance" "production_db" {
  allocated_storage = 100
  instance_class    = "db.r5.2xlarge" # inline comment
}
"""
        result = parser.mutate_instance_spec(
            file_path="main.tf",
            content=content_with_comments,
            resource_type="aws_db_instance",
            resource_name="production_db",
            attribute_name="instance_class",
            new_value="db.r6g.xlarge",
        )
        self.assertEqual(result.old_value, "db.r5.2xlarge")
        self.assertIn('instance_class    = "db.r6g.xlarge"', result.updated_code)
        self.assertIn('# This is a very long comment header', result.updated_code)

    def test_regex_fallback_parse_nested_braces(self):
        parser = TerraformHCLParser()
        nested_tf = """
resource "aws_db_instance" "production_db" {
  instance_class = "db.r5.2xlarge"
  tags = {
    Environment = "production"
    Owner       = "devops"
  }
  storage_encrypted = true
}
"""
        blocks = parser._regex_fallback_parse("main.tf", nested_tf)
        self.assertEqual(len(blocks), 1)
        block = blocks[0]
        self.assertEqual(block.current_attributes.get("storage_encrypted"), True)
        self.assertEqual(block.current_attributes.get("tags", {}).get("Environment"), "production")


if __name__ == "__main__":
    unittest.main()
