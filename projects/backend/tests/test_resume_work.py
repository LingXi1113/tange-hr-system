"""Regression cases for employer recall, date association and false positives."""
import pytest

from common.resume_parser import parse_resume_fields, parse_resume_file_with_text


def work(text):
    return parse_resume_fields(text)["work_experience"]


@pytest.mark.parametrize("company", [
    "广州星河科技", "启程集团", "星辰资本", "腾跃电子商务", "智联工作室",
    "阿里巴巴", "字节跳动", "小红书", "腾讯", "North Star Analytics Ltd.",
])
def test_company_suffixes_and_brands_without_company_word(company):
    records = work(f"工作经历\n2020.03-2022.06\n{company}\n投资经理")
    assert len(records) == 1, records
    assert records[0]["company"] == company
    assert records[0]["start"] == "2020-03"
    assert records[0]["end"] == "2022-06"


@pytest.mark.parametrize("period", [
    "2020.03 - 2022.06", "2020/03 至 2022/06", "2020年3月至2022年6月",
    "2020-03--2022-06", "2020.03－2022.06", "2020.03—2022.06",
    "2020.03.01 - 2022.06.30", "March 2020 to June 2022",
    "2020.03 -\n2022.06", "2020.03\n-\n2022.06",
])
def test_period_formats_and_wrapped_dates(period):
    records = work(f"工作经历\n{period}\n广州星河科技\n投资经理")
    assert len(records) == 1, records
    assert (records[0]["start"], records[0]["end"]) == ("2020-03", "2022-06")


@pytest.mark.parametrize("period", ["2022.07-至今", "2022/07 至今", "Jul 2022 - Present"])
def test_current_employment(period):
    record = work(f"工作经历\n{period}\n星辰资本\n投资经理")[0]
    assert (record["start"], record["end"]) == ("2022-07", "至今")


def test_company_before_dates_is_retained_even_with_responsibilities_after_dates():
    records = work("工作经历\n广州星河科技\n战略投资经理\n2020.03-2022.06\n负责投资分析与尽职调查")
    assert len(records) == 1, records
    assert records[0]["company"] == "广州星河科技"
    assert records[0]["position"] == "战略投资经理"
    assert records[0]["desc"] == "负责投资分析与尽职调查"


def test_dates_and_companies_do_not_cross_between_employers_company_first():
    records = work("""工作经历
北辰科技
投资经理
2020.03-2022.06
负责投资分析
启程集团
销售主管
2022.07-至今
负责客户拓展
""")
    assert [(r["company"], r["start"], r["end"]) for r in records] == [
        ("北辰科技", "2020-03", "2022-06"), ("启程集团", "2022-07", "至今"),
    ]


def test_dates_and_companies_do_not_cross_between_employers_date_first():
    records = work("""工作经历
2020.03-2022.06
投资经理
北辰科技
负责投资分析
2022.07-至今
销售主管
启程集团
负责客户拓展
""")
    assert [(r["company"], r["start"], r["end"]) for r in records] == [
        ("北辰科技", "2020-03", "2022-06"), ("启程集团", "2022-07", "至今"),
    ]


def test_company_can_be_more_than_four_lines_after_period():
    records = work("工作经历\n2020.03-2022.06\n全职\n100-499人\n互联网\n民营\n广州星河科技\n投资经理")
    assert len(records) == 1, records
    assert records[0]["company"] == "广州星河科技"


@pytest.mark.parametrize("line", [
    "2020.03-2022.06 广州星河科技 投资经理",
    "广州星河科技 | 投资经理 | 2020.03-2022.06",
    "2020.03-2022.06 阿里巴巴 投资经理",
    "公司：广州星河科技 | 职位：投资经理 | 2020.03-2022.06",
])
def test_single_line_work_history(line):
    records = work("工作经历\n" + line)
    assert len(records) == 1, records
    assert records[0]["company"] in {"广州星河科技", "阿里巴巴"}
    assert records[0]["position"] == "投资经理"
    assert records[0]["start"] == "2020-03"


@pytest.mark.parametrize("heading", ["工作经历（8年）", "02 工作经历", "工 作 经 历", "Work Experience", "实习经历"])
def test_heading_variations(heading):
    records = work(f"{heading}\n2020.03-2022.06\n启程集团\n投资经理")
    assert len(records) == 1, records
    assert records[0]["company"] == "启程集团"


def test_company_without_dates_is_kept_with_blank_dates_and_quality_warning(monkeypatch):
    text = "姓名：张三\n工作经历\n公司：广州星河科技\n职位：投资经理\n负责战略投资"
    monkeypatch.setattr("common.resume_parser.extract_text_with_method", lambda _: (text, "text", 1.0))
    monkeypatch.setattr("common.resume_ai.is_configured", lambda: False)
    fields, status, _ = parse_resume_file_with_text("resume.pdf")
    assert status == "system"
    assert fields["work_experience"][0]["company"] == "广州星河科技"
    assert fields["work_experience"][0]["start"] == ""
    assert fields["work_experience"][0]["end"] == ""
    assert any("任职时间" in warning for warning in fields["_parse_meta"]["warnings"])


def test_projects_education_and_customer_mentions_are_not_employers():
    records = work("""教育经历
2016-2020
广州示例大学
工作经历
2020.03-2022.06
广州星河科技
投资经理
负责为示例集团提供项目服务
客户：北京样例科技有限公司
项目经历
2021.03-2021.06
某某集团
项目经理
""")
    assert [r["company"] for r in records] == ["广州星河科技"]


@pytest.mark.parametrize("body", [
    "销售专员\n负责销售工作",
    "销售经理\n负责为某某科技有限公司提供服务\n客户：某某集团",
    "投资经理\n业绩提升30%\nPython / React / MongoDB",
])
def test_job_titles_skills_and_descriptions_do_not_become_companies(body):
    assert work("工作经历\n2020.03-2022.06\n" + body) == []


def test_no_heading_keeps_employer_with_date_but_not_project_section():
    records = work("2020.03-2022.06\n广州星河科技\n投资经理\n项目经历\n2021.03-2021.06\n某某集团")
    assert [r["company"] for r in records] == ["广州星河科技"]


def test_repeated_pdf_page_headers_do_not_duplicate_work_records():
    block = "工作经历\n2020.03-2022.06\n启程集团\n投资经理\n"
    assert len(work(block + block)) == 1


def test_company_legal_suffix_wrapped_on_next_line():
    records = work("工作经历\n2020.03-2022.06\n广州星河科技\n有限公司\n投资经理")
    assert [r["company"] for r in records] == ["广州星河科技有限公司"]


def test_ocr_spaced_chinese_company_and_role():
    records = work("工作经历\n2020.03-2022.06\n广 州 星 河 科 技\n投 资 经 理")
    assert records[0]["company"] == "广州星河科技"
    assert records[0]["position"] == "投资经理"


def test_inline_section_heading_and_single_line_company():
    records = work("工作经历：2020.03-2022.06 广州星河科技 投资经理")
    assert len(records) == 1
    assert records[0]["company"] == "广州星河科技"


def test_company_label_without_colon():
    records = work("工作经历\n2020.03-2022.06\n公司名称 星河\n投资经理")
    assert len(records) == 1
    assert records[0]["company"] == "星河"


def test_multiword_english_company_and_role_on_one_line():
    records = work("Work Experience\nMarch 2020 to June 2022 North Star Analytics Investment Manager")
    assert len(records) == 1
    assert records[0]["company"] == "North Star Analytics"
    assert records[0]["position"] == "Investment Manager"


def test_company_only_in_education_is_not_work_experience():
    assert work("教育经历\n2020-2024\n示例大学\n参与某某集团合作项目") == []
