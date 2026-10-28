"""Names must not be inferred from a job's city or salary metadata."""
import pytest

from common.resume_parser import (
    _merge_ai_fields,
    _name_from_filename,
    _resume_quality,
    parse_resume_fields,
)


@pytest.mark.parametrize("filename", [
    "【战略投资（A股上市公司_AI领域）_广州 20-40K】颜瑞 8年.pdf",
    "【战略投资（A股上市公司_AI领域）_广州 20-40K】陆芷欣 8年.pdf",
    "[战略投资（A股上市公司_AI领域）_广州 20-40K]颜瑞 8年.pdf",
    "广州_20-40K_【颜瑞】_8年.pdf",
    "C:\\uploads\\【广州 20-40K】颜瑞 8年.pdf",
])
def test_chinese_brackets_separate_person_from_job_metadata(filename):
    expected = "陆芷欣" if "陆芷欣" in filename else "颜瑞"
    assert _name_from_filename(filename) == expected
    fields = parse_resume_fields("手机：13900000001\n最高学历：硕士", filename)
    assert fields["name"] == expected
    assert "姓名仅来自文件名，建议核对" in _resume_quality(fields, "手机：13900000001\n最高学历：硕士", filename)[1]


@pytest.mark.parametrize("location", ["广州", "广州市", "杭州", "苏州", "武汉", "海口", "广东省", "Hong Kong"])
def test_location_without_name_is_left_empty(location):
    assert _name_from_filename(f"【战略投资_{location}_20-40K】8年.pdf") == ""
    fields = parse_resume_fields(f"{location}\n手机：13900000001", "战略投资.pdf")
    assert fields["name"] == ""


@pytest.mark.parametrize("name", ["张三", "颜瑞", "王轶群", "陆芷欣", "林江", "李杭州", "欧阳娜娜"])
def test_real_names_are_not_rejected_by_partial_city_matches(name):
    assert _name_from_filename(f"广州-战略投资-{name}.pdf") == name


def test_body_header_takes_priority_over_filename_and_city():
    fields = parse_resume_fields("广州\n颜瑞 | 手机：13900000001\n教育背景\n北京大学 硕士", "【广州】张三.pdf")
    assert fields["name"] == "颜瑞"


def test_basic_information_heading_can_precede_name():
    assert parse_resume_fields("个人简历\n基本信息\n颜瑞\n手机：13900000001")["name"] == "颜瑞"


def test_no_guess_from_job_location_salary_or_unrecognized_short_words():
    assert _name_from_filename("【战略投资_广州_20-40K】薪资面议_8年.pdf") == ""
    assert _name_from_filename("【战略投资_广州_20-40K】优秀.pdf") == ""


def test_label_and_ai_names_cannot_bypass_location_validation():
    assert parse_resume_fields("姓名：广州\n手机：13900000001", "【广州】颜瑞.pdf")["name"] == "颜瑞"
    fields = parse_resume_fields("手机：13900000001", "战略投资.pdf")
    assert _merge_ai_fields(fields, {"name": "广州"}, "手机：13900000001", "战略投资.pdf")["name"] == ""
