"""Localize presentation templates before final delivery, without changing bound values."""
import re
from collections import Counter
from string import Formatter


class DeliveryLanguage:
    """校验语言及占位符；语义翻译仍由作者负责，不冒充程序能验证翻译质量。"""
    def __init__(self, language="en", catalog=None):
        if not isinstance(language, str) or not re.fullmatch(r"[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})*", language):
            raise ValueError("report_language must be a BCP-47 language tag")
        self.language = language
        self.english = language.lower().split("-")[0] == "en"
        self.strings = {}
        self.issues = []
        if catalog is not None:
            if (not isinstance(catalog, dict) or set(catalog) != {"report_language", "strings"}
                    or not isinstance(catalog["report_language"], str)
                    or catalog["report_language"].lower() != language.lower()
                    or not isinstance(catalog["strings"], dict)):
                raise ValueError("translation catalog must have matching report_language and a strings object")
            if self.english:
                raise ValueError("English uses the built-in text; do not replace it with a translation catalog")
            self.strings = catalog["strings"]

    @staticmethod
    def fields(template):
        """保留每个占位符的出现次数、转换及格式，禁止属性索引和格式内再插值。"""
        fields = Counter()
        for _, name, spec, conversion in Formatter().parse(template):
            if name is not None:
                if not name.isdigit() or "{" in spec or "}" in spec:
                    raise ValueError("translation placeholders must be positional fields with literal format specs")
                fields[(name, spec, conversion)] += 1
        return fields

    def __call__(self, source, *values):
        """只翻译固定模板，目标、数字、日期、来源和原话随后由脚本插入。"""
        rendered = source
        if not self.english:
            candidate = self.strings.get(source)
            try:
                if not isinstance(candidate, str) or not candidate.strip():
                    raise ValueError("missing nonempty translation")
                if self.fields(candidate) != self.fields(source):
                    raise ValueError("translation changed placeholders or numeric formatting")
                rendered = candidate
            except ValueError as error:
                self.issues.append(f"{error}: {source!r}")
        return rendered.format(*values)

    def validate(self):
        """所有缺项一起返回，校验前不写最终报告或输出可交付标记。"""
        if self.issues:
            raise ValueError("Complete --translations-file before delivery (report_language="
                             + self.language + "): " + "; ".join(dict.fromkeys(self.issues)))
