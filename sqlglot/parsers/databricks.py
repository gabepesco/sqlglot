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

    ALTERABLES = SparkParser.ALTERABLES | {TokenType.SCHEMA, TokenType.DATABASE}

    ALTER_PARSERS = {
        **SparkParser.ALTER_PARSERS,
        "DEFAULT": lambda self: self._parse_alter_schema_default_collation(),
        "OWNER": lambda self: self._parse_alter_schema_owner(),
        "RETAIN": lambda self: self._parse_alter_schema_retain_dropped(),
        "UNSET": lambda self: self._parse_alter_schema_unset_tags(),
        "ENABLE": lambda self: self._parse_alter_schema_predictive_opt("ENABLE"),
        "DISABLE": lambda self: self._parse_alter_schema_predictive_opt("DISABLE"),
        "INHERIT": lambda self: self._parse_alter_schema_predictive_opt("INHERIT"),
    }

    def _parse_alter_table_set(self) -> exp.Expression:
        if self._match_text_seq("DBPROPERTIES"):
            return self.expression(
                exp.AlterSchemaSetDbProperties(
                    expressions=self._parse_wrapped_csv(self._parse_property)
                )
            )
        if self._match_text_seq("TAGS"):
            return self.expression(
                exp.AlterSchemaSetTags(expressions=self._parse_wrapped_csv(self._parse_assignment))
            )
        if self._match_text_seq("DEFAULT", "COLLATION"):
            return self.expression(exp.AlterSchemaDefaultCollation(this=self._parse_field()))
        if self._match_text_seq("MANAGED", "LOCATION"):
            return self.expression(exp.AlterSchemaManagedLocation(this=self._parse_field()))
        if self._match_text_seq("OWNER", "TO"):
            return self.expression(exp.AlterSchemaOwner(this=self._parse_id_var()))
        if self._match_text_seq("RETAIN", "DROPPED", "TO"):
            return self.expression(self._parse_alter_schema_retain_dropped_value())
        return super()._parse_alter_table_set()

    def _parse_alter_schema_default_collation(self) -> exp.Expression:
        self._match_text_seq("COLLATION")
        return self.expression(exp.AlterSchemaDefaultCollation(this=self._parse_field()))

    def _parse_alter_schema_owner(self) -> exp.Expression:
        self._match_text_seq("TO")
        return self.expression(exp.AlterSchemaOwner(this=self._parse_id_var()))

    def _parse_alter_schema_predictive_opt(self, mode: str) -> exp.Expression:
        self._match_text_seq("PREDICTIVE", "OPTIMIZATION")
        return self.expression(exp.AlterSchemaPredictiveOptimization(this=mode))

    def _parse_alter_schema_retain_dropped(self) -> exp.Expression:
        self._match_text_seq("DROPPED", "TO")
        return self._parse_alter_schema_retain_dropped_value()

    def _parse_alter_schema_retain_dropped_value(self) -> exp.Expression:
        number = self._parse_number()
        unit = self._advance_any() and self._prev.text.upper()
        return self.expression(exp.AlterSchemaRetainDropped(this=number, unit=unit))

    def _parse_alter_schema_unset_tags(self) -> exp.Expression:
        self._match_text_seq("TAGS")
        return self.expression(
            exp.AlterSchemaSetTags(
                expressions=self._parse_wrapped_csv(self._parse_string), unset=True
            )
        )

    def _parse_cluster_property(self):
        if self._match_texts(("AUTO", "NONE")):
            return self.expression(exp.ClusterProperty(this=self._prev.text.upper()))
        return super()._parse_cluster_property()
