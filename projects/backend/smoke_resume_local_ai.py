"""Real local OCR and AI checks using generated, fictional resumes."""
import json
from pathlib import Path
import tempfile

from docx import Document
from PIL import Image, ImageDraw, ImageFont

from common.resume_ai import extract_resume_fields, is_configured
from common.resume_parser import parse_resume_file_with_text


def main():
    assert is_configured(), 'Configure local resume AI before running this check.'
    text = '姓名：赵明\n教育背景\n2018.09-2022.06 深圳大学 计算机科学 本科'
    ai_fields, error = extract_resume_fields(text, '软件开发-赵明.pdf')
    assert not error, error
    assert ai_fields.get('name') == '赵明', ai_fields
    assert any('深圳大学' in x.get('school', '') for x in ai_fields.get('education', [])), ai_fields

    results = []
    with tempfile.TemporaryDirectory(prefix='resume-local-ai-') as directory:
        root = Path(directory)
        docx_path = root / '软件开发-赵明.docx'
        document = Document()
        for line in text.splitlines():
            document.add_paragraph(line)
        document.save(docx_path)

        image_path = root / '软件开发-赵明.png'
        image = Image.new('RGB', (1500, 500), 'white')
        draw = ImageDraw.Draw(image)
        font = ImageFont.truetype('C:/Windows/Fonts/msyh.ttc', 42)
        draw.multiline_text((60, 60), text, font=font, fill='black', spacing=35)
        image.save(image_path)
        pdf_path = root / '软件开发-赵明.pdf'
        image.save(pdf_path, 'PDF')
        image.close()

        for path, expected in [(docx_path, 'text+ai'), (image_path, 'ocr+ai'), (pdf_path, 'ocr+ai')]:
            fields, status, source = parse_resume_file_with_text(str(path), path.name)
            assert status == 'system', (path.suffix, fields)
            assert fields.get('name') == '赵明', (path.suffix, fields)
            assert fields['_parse_meta']['method'] == expected, fields['_parse_meta']
            assert source.strip(), path.suffix
            assert any('深圳大学' == x.get('school', '') for x in fields.get('education', [])), (path.suffix, fields)
            results.append({'format': path.suffix, **fields['_parse_meta']})
            print(json.dumps(results[-1], ensure_ascii=True), flush=True)
    print(json.dumps({'ok': True, 'checks': results}, ensure_ascii=True))


if __name__ == '__main__':
    main()

