import type { CandidateDetail, CandidateRow } from '@/services/candidate';
import type { Job } from '@/services/job';
import type { ScreeningResult } from '@/services/screening';

const EDUCATION_RANK: Record<string, number> = {
  高中: 1, 中专: 1, 大专: 2, 本科: 3, 硕士: 4, 博士: 5,
};

function compact(values: Array<string | undefined | null>) {
  return values.map((value) => String(value || '').trim()).filter(Boolean);
}

function candidateSearchText(candidate: CandidateRow) {
  return compact([
    candidate.tags,
    candidate.highest_education,
    candidate.major,
    candidate.education_summary?.school,
    candidate.education_summary?.major,
    candidate.education_summary?.degree,
    candidate.work_summary?.company,
    candidate.work_summary?.position,
    candidate.work_summary?.desc,
  ]).join(' ').toLowerCase();
}

export interface LocalRecommendation {
  candidate: CandidateRow;
  score: number;
  matched: string[];
  missing: string[];
  summary: string;
}

export function rankCandidatesForJob(candidates: CandidateRow[], job: Job): LocalRecommendation[] {
  const rules = job.screening_rules;
  const required = compact([...(rules.required_skills || []), ...(rules.hard_skills || [])]);
  const preferred = compact([...(rules.preferred_skills || []), ...(rules.industry_tags || [])]);

  return candidates.map((candidate) => {
    const text = candidateSearchText(candidate);
    const matchedRequired = required.filter((term) => text.includes(term.toLowerCase()));
    const matchedPreferred = preferred.filter((term) => text.includes(term.toLowerCase()));
    const missing = required.filter((term) => !text.includes(term.toLowerCase()));
    const requiredScore = required.length ? matchedRequired.length / required.length * 55 : 35;
    const preferredScore = preferred.length ? matchedPreferred.length / preferred.length * 25 : 15;
    const minEducation = EDUCATION_RANK[rules.min_education] || 0;
    const candidateEducation = EDUCATION_RANK[candidate.highest_education || candidate.education_summary?.degree || ''] || 0;
    const educationScore = !minEducation || candidateEducation >= minEducation ? 10 : 2;
    const titleScore = job.name && text.includes(job.name.toLowerCase()) ? 10 : 4;
    const score = Math.min(100, Math.round(requiredScore + preferredScore + educationScore + titleScore));
    const matched = [...new Set([...matchedRequired, ...matchedPreferred])];
    return {
      candidate,
      score,
      matched,
      missing,
      summary: matched.length
        ? `命中 ${matched.slice(0, 3).join('、')}，建议 HR 进一步核实项目深度和实际成果。`
        : '当前结构化信息命中较少，建议结合原始简历人工确认。',
    };
  }).sort((a, b) => b.score - a.score);
}

export function buildCandidateAssistantReply(
  question: string,
  candidate: CandidateDetail,
  screening: ScreeningResult | null,
) {
  const latestWork = candidate.work_experience?.[0] || candidate.work_summary || {};
  const education = candidate.education?.[0] || candidate.education_summary || {};
  const matched = screening?.matched_items || [];
  const missing = screening?.missing_items || [];
  const normalized = question.toLowerCase();

  if (/总结|概括|介绍|简历/.test(normalized)) {
    return `${candidate.name}，${candidate.highest_education || education.degree || '学历待确认'}，专业为${candidate.major || education.major || '待确认'}。最近经历为${latestWork.company || '公司待确认'}${latestWork.position ? `的${latestWork.position}` : ''}。${candidate.tags ? `当前标签包括：${candidate.tags}。` : ''}${screening ? `与“${screening.job_name}”的本地匹配度为 ${screening.score}%。` : ''}`;
  }
  if (/匹配|岗位|适合|符合/.test(normalized)) {
    if (!screening) return '当前还没有职位匹配结果。请先点击“投递职位匹配”选择岗位，生成结果后我可以继续解释符合项与差距。';
    return `当前匹配岗位为“${screening.job_name}”，综合得分 ${screening.score}%，系统建议为“${screening.decision_label}”。${matched.length ? `主要符合项：${matched.slice(0, 5).join('；')}。` : ''}${missing.length ? `需要进一步确认：${missing.slice(0, 4).join('；')}。` : '暂未发现明显缺失项。'}`;
  }
  if (/问题|面试|追问/.test(normalized)) {
    const focus = missing.length ? missing.slice(0, 3) : matched.slice(0, 3);
    return `建议重点提问：\n1. 请介绍一个最能体现你${focus[0] || '核心能力'}的项目，并说明个人贡献。\n2. 遇到目标未达成时，你如何定位问题并推动改进？\n3. ${focus[1] ? `请具体说明你在“${focus[1]}”方面的实操经验。` : '请说明上一段经历中可量化的业务成果。'}\n4. 为什么考虑当前岗位，你希望解决什么类型的问题？`;
  }
  if (/风险|不足|缺失|注意/.test(normalized)) {
    return missing.length
      ? `建议人工核实以下内容：${missing.slice(0, 6).join('；')}。这些是信息缺失或待确认项，不代表候选人一定不符合。`
      : '结构化资料中暂未发现明显风险。仍建议核实工作时间连续性、项目真实性、个人贡献及求职动机。';
  }
  return `我已结合当前候选人的基本资料${screening ? `和“${screening.job_name}”匹配结果` : ''}进行分析。你可以问我：概括候选人、解释岗位匹配度、生成面试问题，或列出待核实风险。当前为本地演示模式，结论仅供 HR 参考。`;
}

export function buildJobPortrait(job: Job) {
  const rules = job.screening_rules;
  const saved = job.ai_portrait;
  if (saved?.summary || saved?.required?.length || saved?.preferred?.length || saved?.interview_focus?.length) {
    return {
      title: job.name,
      summary: saved.summary || job.description || `负责${job.name}相关工作。`,
      required: saved.required || [],
      preferred: saved.preferred || [],
      interviewFocus: saved.interview_focus || [],
    };
  }
  return {
    title: job.name,
    summary: job.description || `负责${job.name}相关工作，围绕业务目标交付可衡量结果。`,
    required: compact([
      rules.min_education ? `学历不低于${rules.min_education}` : '',
      rules.min_work_years ? `相关经验不少于${rules.min_work_years}年` : '',
      ...(rules.hard_skills || []),
      ...(rules.required_skills || []),
    ]),
    preferred: compact([...(rules.preferred_skills || []), ...(rules.industry_tags || [])]),
    interviewFocus: compact([
      ...(rules.required_skills || []).slice(0, 3),
      '项目中的个人贡献', '可量化业务成果', '岗位动机与稳定性',
    ]),
  };
}
