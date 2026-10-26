"""Degree distinctions, multi-column education and conservative AI repair."""
import pytest

from common.resume_parser import (
    _extract_pdf, _merge_ai_fields, _pdf_rows, highest_education_from_records,
    normalize_degree, parse_resume_fields,
)


@pytest.mark.parametrize(("raw", "expected"), [
    ("工科/硕士", "硕士"), ("理科/学士", "本科"), ("博士研究生", "博士"),
    ("Master of Science", "硕士"), ("M.Sc.", "硕士"), ("M.Eng.", "硕士"),
    ("MBA", "硕士"), ("EMBA", "硕士"), ("Ph.D.", "博士"), ("PhD", "博士"),
    ("Doctor of Philosophy", "博士"), ("DPhil", "博士"),
    ("Bachelor of Engineering", "本科"), ("B.Sc.", "本科"),
    ("研究生", ""), ("在职研究生", ""), ("博士后", ""), ("postdoctoral", ""),
])
def test_normalize_distinguishes_degrees_without_guessing(raw, expected):
    assert normalize_degree(raw) == expected


def test_user_example_same_row_degree_and_major():
    fields = parse_resume_fields("""教育背景
2016.09-2018.07 北京大学 金融信息服务 工科/硕士
2011.09-2015.06 武汉大学 金融工程 理科/学士
工作经历
""")
    assert fields["education"] == [
        {"school": "北京大学", "major": "金融信息服务", "degree": "硕士", "graduate_at": "2018-07"},
        {"school": "武汉大学", "major": "金融工程", "degree": "本科", "graduate_at": "2015-06"},
    ]
    assert fields["highest_education"] == "硕士"
    assert fields["major"] == "金融信息服务"


def test_user_example_detached_master_column():
    fields = parse_resume_fields("""教育背景
2016.09-2018.07 北京大学 金融信息服务
2011.09-2015.06 武汉大学 金融工程 理科/学士
工科/硕士
工作经历
""")
    assert [(item["school"], item["degree"]) for item in fields["education"]] == [("北京大学", "硕士"), ("武汉大学", "本科")]
    assert fields["highest_education"] == "硕士"


def test_complete_detached_degree_column_retains_order():
    fields = parse_resume_fields("""教育经历
2020-2024 清华大学 人工智能
2018-2020 北京大学 计算机
2014-2018 武汉大学 软件工程
博士
硕士
本科
工作经历
""")
    assert [item["degree"] for item in fields["education"]] == ["博士", "硕士", "本科"]
    assert fields["highest_education"] == "博士"


def test_degree_farther_than_two_lines_and_faculty_is_not_a_new_school():
    fields = parse_resume_fields("""教育经历
2018-2022 武汉大学 计算机 本科
2022-2025 清华大学
管理学院
研究方向：企业数字化
全日制
硕士
工作经历
岗位要求：博士
""")
    assert len(fields["education"]) == 2
    assert fields["education"][1]["degree"] == "硕士"
    assert fields["highest_education"] == "硕士"


def test_same_university_higher_sparse_record_is_not_discarded():
    fields = parse_resume_fields("""教育经历
2010-2014 武汉大学 软件工程 本科
2014-2017 武汉大学 硕士
2017-2021 武汉大学 博士
""")
    assert [item["degree"] for item in fields["education"]] == ["本科", "硕士", "博士"]
    assert fields["highest_education"] == "博士"


def test_english_school_and_degree_are_recognized():
    fields = parse_resume_fields("""Education
2012-2016 武汉大学 | 计算机 | 本科
2016-2018 University of Leeds | Data Science | M.Sc.
2018-2022 Stanford University | Computer Science | Ph.D.
Work Experience
""")
    assert [item["degree"] for item in fields["education"]] == ["本科", "硕士", "博士"]
    assert fields["highest_education"] == "博士"


def test_ai_supplements_master_instead_of_freezing_undergraduate_record():
    text = "教育经历\n2012-2016 武汉大学 本科\n2016-2018 北京大学 金融 硕士"
    fields = {"education": [{"school": "武汉大学", "degree": "本科", "graduate_at": "2016"}], "highest_education": "本科"}
    merged = _merge_ai_fields(fields, {"education": [{"school": "北京大学", "degree": "硕士", "major": "金融", "graduate_at": "2018"}]}, text, "")
    assert [item["degree"] for item in merged["education"]] == ["本科", "硕士"]
    assert merged["highest_education"] == "硕士"


def test_ai_cannot_promote_degree_using_work_requirement_or_invented_degree():
    text = "教育经历\n2012-2016 武汉大学 本科\n工作经历\n北京大学合作项目，岗位要求博士"
    fields = parse_resume_fields(text)
    merged = _merge_ai_fields(fields, {"education": [
        {"school": "武汉大学", "degree": "博士"}, {"school": "北京大学", "degree": "博士"},
    ]}, text, "")
    assert merged["highest_education"] == "本科"
    assert len(merged["education"]) == 1


def test_ai_repairs_wrong_degree_only_for_same_evidenced_school_period():
    text = "教育经历\n2016-2018 北京大学 金融 硕士"
    fields = {"education": [{"school": "北京大学", "degree": "本科", "graduate_at": "2018"}]}
    merged = _merge_ai_fields(fields, {"education": [{"school": "北京大学", "degree": "硕士", "graduate_at": "2018"}]}, text, "")
    assert len(merged["education"]) == 1
    assert merged["education"][0]["degree"] == "硕士"
    assert merged["highest_education"] == "硕士"


def test_explicit_personal_highest_education_is_not_downgraded():
    assert highest_education_from_records([{"degree": "本科"}], "最高学历：硕士") == "硕士"


def test_pdf_row_separators_do_not_hide_section_boundaries():
    fields = parse_resume_fields("教育背景 | 2010-2014 武汉大学 本科\n工作经历 | 北京大学合作项目，要求博士")
    assert fields["highest_education"] == "本科"
    assert len(fields["education"]) == 1


def test_advisor_doctorate_does_not_promote_candidates_master():
    fields = parse_resume_fields("教育经历\n2016-2018 北京大学 金融 硕士 导师：博士生导师\n工作经历")
    assert fields["education"][0]["degree"] == "硕士"
    assert fields["highest_education"] == "硕士"


def test_ambiguous_detached_degree_column_is_not_assigned_to_wrong_school():
    fields = parse_resume_fields("教育背景\n2016-2018 北京大学\n2012-2016 武汉大学\n硕士\n工作经历")
    assert [record["degree"] for record in fields["education"]] == ["", ""]


class Fragment:
    def __init__(self, x, y, value):
        self.x0, self.y0, self.y1, self.height = x, y, y + 10, 10
        self.value = value

    def get_text(self):
        return self.value


def test_pdf_visual_row_restores_school_degree_association(monkeypatch):
    monkeypatch.setattr("pdfminer.layout.LTTextLine", Fragment)
    # The storage/column order is deliberately unrelated to visual reading order.
    layout = [
        [Fragment(500, 700, "工科/硕士"), Fragment(500, 650, "理科/学士")],
        [Fragment(120, 700, "北京大学"), Fragment(120, 650, "武汉大学")],
        [Fragment(300, 700, "金融信息服务"), Fragment(300, 650, "金融工程")],
        [Fragment(0, 700, "2016.09-2018.07"), Fragment(0, 650, "2011.09-2015.06")],
    ]
    rows = _pdf_rows(layout)
    assert rows == ["2016.09-2018.07 | 北京大学 | 金融信息服务 | 工科/硕士", "2011.09-2015.06 | 武汉大学 | 金融工程 | 理科/学士"]
    monkeypatch.setattr("pdfminer.high_level.extract_pages", lambda *args, **kwargs: [layout])
    fields = parse_resume_fields("教育背景\n" + _extract_pdf("unused.pdf"))
    assert [item["degree"] for item in fields["education"]] == ["硕士", "本科"]
    assert fields["highest_education"] == "硕士"
