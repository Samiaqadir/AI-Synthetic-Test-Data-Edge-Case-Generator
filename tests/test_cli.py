"""Integration tests for Samia CLI commands."""

from click.testing import CliRunner

from samia.cli import cli


def test_cli_help():
    runner = CliRunner()
    result = runner.invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert "Samia: AI Synthetic Test Data & Edge-Case Generator CLI" in result.output


def test_cli_inspect_sql():
    runner = CliRunner()
    result = runner.invoke(cli, ["inspect", "--schema-sql", "examples/ecommerce.sql"])
    assert result.exit_code == 0
    assert "Topological Generation Order" in result.output
    assert "users" in result.output


def test_cli_generate_mixed(tmp_path):
    runner = CliRunner()
    out_dir = str(tmp_path / "out")
    result = runner.invoke(
        cli,
        [
            "generate",
            "--schema-sql",
            "examples/ecommerce.sql",
            "--mode",
            "mixed",
            "--count",
            "5",
            "--output-dir",
            out_dir,
            "--format",
            "all",
        ],
    )
    assert result.exit_code == 0
    assert "Successfully generated" in result.output
    assert (tmp_path / "out" / "synthetic_data.json").exists()
    assert (tmp_path / "out" / "inserts.sql").exists()
    assert (tmp_path / "out" / "validation_report.json").exists()


def test_cli_validate_existing(tmp_path):
    runner = CliRunner()
    out_dir = str(tmp_path / "out")
    # First generate
    runner.invoke(
        cli,
        [
            "generate",
            "--schema-sql",
            "examples/ecommerce.sql",
            "--mode",
            "happy",
            "--count",
            "5",
            "--output-dir",
            out_dir,
        ],
    )

    data_file = str(tmp_path / "out" / "synthetic_data.json")
    rep_file = str(tmp_path / "out" / "val_rep.json")

    # Then validate
    val_res = runner.invoke(
        cli,
        [
            "validate",
            "--data",
            data_file,
            "--schema-sql",
            "examples/ecommerce.sql",
            "--report",
            rep_file,
        ],
    )
    assert val_res.exit_code == 0
    assert "Validation Results" in val_res.output
