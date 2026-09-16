from datetime import date

from common.resume_parser import parse_resume_fields


def test_resume_parser_extracts_age_highest_education_and_major():
    fields = parse_resume_fields("""
姓名：张三
性别：男
年龄：28岁
教育经历
2015.09-2019.06 华东理工大学 计算机科学与技术 本科
2019.09-2022.06 中山大学 软件工程 硕士研究生
""")

    assert fields["age"] == 28
    assert fields["highest_education"] == "硕士"
    assert fields["major"] == "软件工程"
    assert fields["education"][0]["degree"] == "本科"
    assert fields["education"][1]["degree"] == "硕士"


def test_resume_parser_derives_age_from_birth_date_and_labelled_major():
    fields = parse_resume_fields("""
姓名：李四
出生日期：1998-10-20
教育经历
2017-2021 广东工业大学
专业：市场营销
学历：本科
""")

    expected_age = date.today().year - 1998 - (
        (date.today().month, date.today().day) < (10, 20)
    )
    assert fields["age"] == expected_age
    assert fields["highest_education"] == "本科"
    assert fields["major"] == "市场营销"


def test_resume_parser_normalizes_pdf_radicals_and_separates_school_department_major():
    fields = parse_resume_fields("""
卢思源
男 21岁
中⼭⼤学东校园
教育背景
中⼭⼤学（985） 计算机学院/计算机科学与技术 本科 GPA: 3.3/4.0
2023-09 - 2027-06
""")

    assert fields["education"] == [{
        "school": "中山大学",
        "major": "计算机科学与技术",
        "degree": "本科",
        "graduate_at": "2027-06",
    }]
    assert fields["highest_education"] == "本科"
    assert fields["major"] == "计算机科学与技术"


def test_resume_parser_infers_vocational_college_degree_and_year_range():
    fields = parse_resume_fields("""
教育经历
海南职业技术学院 | 工程造价 | 2021-2024
资格证书
驾驶证 C1
""")

    assert fields["education"] == [{
        "school": "海南职业技术学院",
        "major": "工程造价",
        "degree": "大专",
        "graduate_at": "2024",
    }]
    assert fields["highest_education"] == "大专"
    assert fields["major"] == "工程造价"
