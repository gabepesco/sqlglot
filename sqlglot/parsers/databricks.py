from __future__ import annotations

from sqlglot import exp, parser
from sqlglot.dialects.dialect import build_date_delta, build_formatted_time
from sqlglot.helper import seq_get
from sqlglot.parsers.spark import SparkParser
from sqlglot.tokens import TokenType


class DatabricksParser(SparkParser):
    LOG_DEFAULTS_TO_LN = True
    STRICT_CAST = True
    COLON_IS_VARIANT_EXTRACT = True
    COLON_CHAIN_IS_SINGLE_EXTRACT = False

    ALTERABLES = SparkParser.ALTERABLES | {TokenType.SCHEMA, TokenType.DATABASE}

    ALTER_PARSERS = {
        **SparkParser.ALTER_PARSERS,
        "OWNER": lambda self: self._parse_alter_schema_owner(),
        "SET": lambda self: self._parse_databricks_alter_set(),
        "UNSET": lambda self: self.expression(
            exp.Set(
                tag=self._match_text_seq("TAGS"),
                expressions=self._parse_wrapped_csv(self._parse_string),
                unset=True,
            )
        ),
    }

    FUNCTIONS = {
        **SparkParser.FUNCTIONS,
        "IFF": exp.If.from_arg_list,
        "GETDATE": exp.CurrentTimestamp.from_arg_list,
        "DATEDIFF": build_date_delta(exp.DateDiff),
        "DATE_DIFF": build_date_delta(exp.DateDiff),
        "NOW": exp.CurrentTimestamp.from_arg_list,
        "TO_DATE": build_formatted_time(exp.TsOrDsToDate),
        "UNIFORM": lambda args: exp.Uniform(
            this=seq_get(args, 0), expression=seq_get(args, 1), seed=seq_get(args, 2)
        ),
    }

    NO_PAREN_FUNCTION_PARSERS = {
        **SparkParser.NO_PAREN_FUNCTION_PARSERS,
        "CURDATE": lambda self: self._parse_curdate(),
    }

    FACTOR = {
        **SparkParser.FACTOR,
        TokenType.COLON: exp.JSONExtract,
    }

    COLUMN_OPERATORS = {
        **parser.Parser.COLUMN_OPERATORS,
        TokenType.QDCOLON: lambda self, this, to: self.build_cast(
            False,
            this=this,
            to=to,
        ),
    }
    CAST_COLUMN_OPERATORS = {
        *SparkParser.CAST_COLUMN_OPERATORS,
        TokenType.QDCOLON,
    }

    def _parse_curdate(self) -> exp.CurrentDate:
        # CURDATE, an alias for CURRENT_DATE, has optional parentheses
        if self._match(TokenType.L_PAREN):
            self._match_r_paren()
        return self.expression(exp.CurrentDate())

    def _parse_cluster_property(self):
        if self._match_texts(("AUTO", "NONE")):
            return self.expression(exp.ClusterProperty(this=self._prev.text.upper()))
        return super()._parse_cluster_property()

    def _parse_alter_schema_owner(self):
        self._match_text_seq("TO")
        return self.expression(exp.AlterSchemaOwner(this=self._parse_id_var()))

    def _parse_databricks_alter_set(self):
        if self._match_text_seq("OWNER", "TO"):
            return self.expression(exp.AlterSchemaOwner(this=self._parse_id_var()))
        if self._match_text_seq("TAGS"):
            return self.expression(exp.AlterSet(tag=self._parse_wrapped_csv(self._parse_conjunction)))
        return self._parse_alter_table_set()
