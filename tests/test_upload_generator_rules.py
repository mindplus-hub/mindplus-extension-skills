"""`addInclude` 实参必须是裸头文件名。

运行时实现（Mind+ upload-gui generator，2026-09-15 从安装目录核对）：

    addInclude(id)        -> #include <id>
    addInclude(id, code)  -> #include "code"

两个实参都被原样塞进指令，所以写成 V1 的整条指令形态会生成
`#include "#include <DFRobot_DHT.h>"`。这里守住字符串字面量；计算得来的实参不判断。
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "switch"))
from check_converted_extension import check_add_include_calls  # noqa: E402


class AddIncludeArgumentTests(unittest.TestCase):
    def test_correct_forms_have_no_findings(self):
        text = """
        generator.addInclude('DFRobot_BMP58X.h');
        generator.addInclude('THS', 'DFRobot_DHT.h');
        generator.addInclude('MPython.h', 'lib/MPython.h');
        generator.addInclude('oled', 'oled.h');
        """
        self.assertEqual(check_add_include_calls(text), [])

    def test_v1_directive_shape_is_flagged(self):
        text = "generator.addInclude('THS', '#include <DFRobot_DHT.h>');"
        findings = check_add_include_calls(text)
        self.assertEqual([item["code"] for item in findings], ["ADD_INCLUDE_CODE_IS_INCLUDE_DIRECTIVE"])
        self.assertEqual(findings[0]["id"], "THS")
        self.assertEqual(findings[0]["code_argument"], "#include <DFRobot_DHT.h>")

    def test_quoted_directive_shape_is_flagged(self):
        text = "generator.addInclude('oled', '#include \"oled.h\"');"
        findings = check_add_include_calls(text)
        self.assertEqual([item["code"] for item in findings], ["ADD_INCLUDE_CODE_IS_INCLUDE_DIRECTIVE"])

    def test_angle_brackets_in_second_argument_are_flagged(self):
        text = "generator.addInclude('THS', '<DFRobot_DHT.h>');"
        findings = check_add_include_calls(text)
        self.assertEqual([item["code"] for item in findings], ["ADD_INCLUDE_CODE_IS_INCLUDE_DIRECTIVE"])

    def test_one_argument_with_brackets_is_flagged(self):
        text = "generator.addInclude('<DFRobot_DHT.h>');"
        findings = check_add_include_calls(text)
        self.assertEqual([item["code"] for item in findings], ["ADD_INCLUDE_ID_NOT_BARE_HEADER"])

    def test_one_argument_with_directive_is_flagged(self):
        text = "generator.addInclude('#include <DFRobot_DHT.h>');"
        findings = check_add_include_calls(text)
        self.assertEqual([item["code"] for item in findings], ["ADD_INCLUDE_ID_NOT_BARE_HEADER"])

    def test_computed_argument_is_left_alone(self):
        text = """
        generator.addInclude('IR_BREAK', irDecodeInclude(irNumber));
        generator.addInclude(headerName);
        """
        self.assertEqual(check_add_include_calls(text), [])

    def test_multiple_calls_report_only_the_bad_one(self):
        text = """
        generator.addInclude('good.h');
        generator.addInclude('bad', '#include <bad.h>');
        generator.addInclude('also good', 'good2.h');
        """
        findings = check_add_include_calls(text)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["id"], "bad")


if __name__ == "__main__":
    unittest.main()
