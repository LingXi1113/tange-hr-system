$ErrorActionPreference = 'Stop'

$BaseUrl = 'http://127.0.0.1:8100'
$Suffix = Get-Date -Format 'yyyyMMddHHmmss'
$Headers = @{}

function Invoke-Api {
    param(
        [Parameter(Mandatory = $true)][string]$Method,
        [Parameter(Mandatory = $true)][string]$Path,
        [object]$Body,
        [switch]$NoAuth
    )

    $params = @{
        Method = $Method
        Uri = "$BaseUrl$Path"
        UseBasicParsing = $true
    }
    if (-not $NoAuth) {
        $params.Headers = $Headers
    }
    if ($null -ne $Body) {
        $params.ContentType = 'application/json; charset=utf-8'
        $params.Body = ($Body | ConvertTo-Json -Depth 20 -Compress)
    }
    $response = Invoke-RestMethod @params
    if ($response.code -ne 0) {
        throw "API $Method $Path failed: code=$($response.code), msg=$($response.msg)"
    }
    return $response.data
}

function Assert-True {
    param([bool]$Condition, [string]$Message)
    if (-not $Condition) { throw "ASSERT FAILED: $Message" }
}

Write-Host "[1/9] Login as HR demo user"
$login = Invoke-Api -Method Post -Path '/api/auth/mock-login' -Body @{ user_id = 'hr-001' } -NoAuth
Assert-True (-not [string]::IsNullOrWhiteSpace($login.token)) 'mock login token is empty'
$Headers['X-Auth-Token'] = $login.token

Write-Host "[2/9] Create and verify three test jobs"
$job1 = Invoke-Api -Method Post -Path '/api/jobs' -Body @{
    code = "TEST-BE-$Suffix"
    name = "TEST-Backend-Engineer-$Suffix"
    dept_id = 'dept-tech'
    dept_name = 'TEST Technology'
    location = 'Shanghai'
    job_type = 'full_time'
    level = 'P6'
    headcount = 2
    salary_range = '25k-40k'
    description = 'TEST backend service development position'
    qualification = 'Python, Flask, MongoDB'
    skill_tags = 'Python,Flask,MongoDB'
    channels = 'website,job_site'
}
$job1 = Invoke-Api -Method Post -Path "/api/jobs/$($job1.id)/status" -Body @{ action = 'submit' }
$job1 = Invoke-Api -Method Post -Path "/api/jobs/$($job1.id)/status" -Body @{ action = 'publish' }

$job2 = Invoke-Api -Method Post -Path '/api/jobs' -Body @{
    code = "TEST-PM-$Suffix"
    name = "TEST-Product-Manager-$Suffix"
    dept_id = 'dept-product'
    dept_name = 'TEST Product'
    location = 'Beijing'
    job_type = 'full_time'
    level = 'P5'
    headcount = 1
    salary_range = '20k-35k'
    description = 'TEST product planning and delivery position'
    qualification = 'Product design and project management'
    skill_tags = 'Product,Project,User Research'
    channels = 'website,referral'
}
$job2 = Invoke-Api -Method Post -Path "/api/jobs/$($job2.id)/status" -Body @{ action = 'submit' }
$job2 = Invoke-Api -Method Post -Path "/api/jobs/$($job2.id)/status" -Body @{ action = 'publish' }

$job3 = Invoke-Api -Method Post -Path '/api/jobs' -Body @{
    code = "TEST-FE-$Suffix"
    name = "TEST-Frontend-Engineer-$Suffix"
    dept_id = 'dept-tech'
    dept_name = 'TEST Technology'
    location = 'Shenzhen'
    job_type = 'full_time'
    level = 'P5'
    headcount = 1
    salary_range = '18k-30k'
    description = 'TEST frontend application development position'
    qualification = 'React, TypeScript, Vite'
    skill_tags = 'React,TypeScript,Vite'
    channels = 'job_site'
}
$job3 = Invoke-Api -Method Post -Path "/api/jobs/$($job3.id)/status" -Body @{ action = 'submit' }
$job3 = Invoke-Api -Method Post -Path "/api/jobs/$($job3.id)/status" -Body @{ action = 'publish' }
$job3 = Invoke-Api -Method Post -Path "/api/jobs/$($job3.id)/status" -Body @{ action = 'pause' }
Assert-True ($job1.status -eq 'recruiting') 'job 1 did not reach recruiting'
Assert-True ($job2.status -eq 'recruiting') 'job 2 did not reach recruiting'
Assert-True ($job3.status -eq 'paused') 'job 3 did not reach paused'

Write-Host "[3/9] Create four test candidates"
$candidatePayloads = @(
    @{ name = "TEST-Candidate-A-$Suffix"; gender = 'M'; phone = "139$($Suffix.Substring(6,8))"; email = "test.a.$Suffix@example.com"; city = 'Shanghai'; tags = 'TEST,backend,senior'; source = 'manual'; remark = 'TEST smoke data A'; education = @(@{ school = 'TEST University'; major = 'Computer Science'; degree = 'Bachelor'; graduate_at = '2020-06' }); work_experience = @(@{ company = 'TEST Cloud'; position = 'Backend Engineer'; start = '2020-07'; end = '2024-12'; desc = 'API and data platform development' }) }
    @{ name = "TEST-Candidate-B-$Suffix"; gender = 'F'; phone = "138$($Suffix.Substring(6,8))"; email = "test.b.$Suffix@example.com"; city = 'Beijing'; tags = 'TEST,product'; source = 'referral'; remark = 'TEST smoke data B'; education = @(@{ school = 'TEST Business School'; major = 'Information Management'; degree = 'Master'; graduate_at = '2019-06' }); work_experience = @(@{ company = 'TEST Product'; position = 'Product Manager'; start = '2019-07'; end = '2025-01'; desc = 'Product planning and delivery' }) }
    @{ name = "TEST-Candidate-C-$Suffix"; gender = 'M'; phone = "137$($Suffix.Substring(6,8))"; email = "test.c.$Suffix@example.com"; city = 'Shenzhen'; tags = 'TEST,frontend,react'; source = 'job_site'; remark = 'TEST smoke data C'; education = @(@{ school = 'TEST Institute'; major = 'Software Engineering'; degree = 'Bachelor'; graduate_at = '2021-06' }); work_experience = @(@{ company = 'TEST Web'; position = 'Frontend Engineer'; start = '2021-07'; end = '2025-02'; desc = 'React and TypeScript development' }) }
    @{ name = "TEST-Candidate-D-$Suffix"; gender = 'F'; phone = "136$($Suffix.Substring(6,8))"; email = "test.d.$Suffix@example.com"; city = 'Guangzhou'; tags = 'TEST,backend,go'; source = 'website'; remark = 'TEST smoke data D'; education = @(@{ school = 'TEST Engineering'; major = 'Computer Engineering'; degree = 'Bachelor'; graduate_at = '2022-06' }); work_experience = @(@{ company = 'TEST Systems'; position = 'Software Engineer'; start = '2022-07'; end = '2025-03'; desc = 'Distributed systems development' }) }
)
$candidates = @()
foreach ($payload in $candidatePayloads) {
    $result = Invoke-Api -Method Post -Path '/api/candidates' -Body $payload
    Assert-True (-not $result.duplicated) "candidate $($payload.name) unexpectedly duplicated"
    $candidates += $result.candidate
}

Write-Host "[4/9] Verify candidate duplicate detection"
$duplicate = Invoke-Api -Method Post -Path '/api/candidates' -Body @{ name = 'TEST-Duplicate-Probe'; phone = $candidatePayloads[0].phone; email = 'duplicate-probe@example.com' }
Assert-True $duplicate.duplicated 'duplicate candidate detection did not trigger'

Write-Host "[5/9] Create applications and test candidate/job relations"
$app1 = Invoke-Api -Method Post -Path "/api/candidates/$($candidates[0].id)/applications" -Body @{ job_id = $job1.id; source = 'manual' }
$app2 = Invoke-Api -Method Post -Path "/api/candidates/$($candidates[1].id)/applications" -Body @{ job_id = $job1.id; source = 'referral' }
$app3 = Invoke-Api -Method Post -Path "/api/candidates/$($candidates[2].id)/applications" -Body @{ job_id = $job2.id; source = 'job_site' }
$app4 = Invoke-Api -Method Post -Path "/api/candidates/$($candidates[3].id)/applications" -Body @{ job_id = $job2.id; source = 'website' }
Assert-True ($app1.current_stage -eq 'new_resume') 'new application stage is incorrect'

Write-Host "[6/9] Move one application through the pipeline"
$moved = Invoke-Api -Method Post -Path "/api/applications/$($app1.id)/move" -Body @{ to_stage = 'pending_screen'; reason = 'TEST smoke stage transition'; version = $app1.version }
Assert-True ($moved.current_stage -eq 'pending_screen') 'application did not move to pending_screen'
Assert-True ($moved.version -eq ($app1.version + 1)) 'application version was not incremented'

Write-Host "[7/9] Eliminate one application and verify the board"
$eliminated = Invoke-Api -Method Post -Path "/api/applications/$($app2.id)/eliminate" -Body @{ reason = 'TEST smoke elimination' }
Assert-True ($eliminated.status -eq 'eliminated') 'application was not eliminated'
$board = Invoke-Api -Method Get -Path "/api/pipeline/board?job_id=$($job1.id)"
Assert-True ($board.cards.Count -ge 1) 'pipeline board has no cards after applications were created'

Write-Host "[8/9] Verify list/detail/public endpoints"
$jobList = Invoke-Api -Method Get -Path "/api/jobs?page_size=100"
$candidateList = Invoke-Api -Method Get -Path "/api/candidates?keyword=TEST-Candidate&page_size=20"
$jobDetail = Invoke-Api -Method Get -Path "/api/jobs/$($job1.id)"
$candidateDetail = Invoke-Api -Method Get -Path "/api/candidates/$($candidates[0].id)"
$publicJob = Invoke-Api -Method Get -Path "/api/public/jobs/$($job1.public_token)" -NoAuth
Assert-True ($jobList.total -ge 3) 'job list does not contain the created test jobs'
Assert-True ($candidateList.total -ge 4) 'candidate list does not contain the created test candidates'
Assert-True ($jobDetail.application_count -ge 2) 'job detail application count is incorrect'
Assert-True ($candidateDetail.applications.Count -ge 1) 'candidate detail has no applications'
Assert-True ($publicJob.name -eq $job1.name) 'public job endpoint returned the wrong job'

Write-Host "[9/9] Final database-backed counts"
$summary = [ordered]@{
    suffix = $Suffix
    jobs_created = 3
    candidates_created = 4
    applications_created = 4
    job_ids = @($job1.id, $job2.id, $job3.id)
    candidate_ids = @($candidates | ForEach-Object { $_.id })
    application_ids = @($app1.id, $app2.id, $app3.id, $app4.id)
    transitioned_application_id = $app1.id
    eliminated_application_id = $app2.id
    board_cards = $board.cards.Count
    job_list_total = $jobList.total
    candidate_list_total = $candidateList.total
    database_status = 'verified through authenticated CRUD and relation queries'
}
$summary | ConvertTo-Json -Depth 10
Write-Host 'LOCAL_SMOKE_TEST_PASS'
