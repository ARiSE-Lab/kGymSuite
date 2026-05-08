"""KBDr-Runner Syzbot Dataset and Benchmark Utilities.

This module provides comprehensive tools for working with Syzbot crash data:
- Data models for Syzbot bug reports, crashes, and reproducers
- Crawlers for fetching data from Syzbot website
- Dataset populators for enriching bug data with git commits and patches
- Benchmark utilities (kBench) for evaluating crash reproduction
- LLM-based patch evaluation

Key Classes:
    SyzbotData: Complete bug report including crashes, patches, and metadata
    SyzbotDataset: Collection of bug reports
    SyzbotCrawler: Web crawler for Syzbot bug database
    SyzbotPopulator: Enriches bug data with git repository information
    kBench: Benchmark evaluation framework for crash reproduction

Example:
    Loading and evaluating a benchmark:

    >>> from KBDr.kclient import kGymAsyncClient, kBench
    >>>
    >>> # Load pre-built benchmark
    >>> bench = kBench.load("benchmark.json")
    >>>
    >>> # Run evaluation
    >>> async with kGymAsyncClient("http://localhost:8000") as client:
    ...     results = await bench.evaluate_kgym(
    ...         client,
    ...         timeout=3600,
    ...         userspace_image="buildroot.raw"
    ...     )
    ...     for bug_id, result in results.root.items():
    ...         print(f"{bug_id}: {result.evaluation}")
"""

from pydantic import BaseModel, Field, ConfigDict, RootModel
from pydantic_core import to_json, from_json
from typing import List, Dict, Any, Literal, Union, Tuple
from copy import deepcopy
from datetime import datetime
from lxml.html import fromstring
from KBDr.kcore import run_async, JobId, JobResource, JobStatus
import requests, asyncio
import asyncio.subprocess as asp
from collections import defaultdict
from pydriller import Repository, Commit
from ..kclient_models.kvmmanager import *
from ..kclient_models.kbuilder import *
from .models import kJobRequest, kJobContext
import litellm
from tqdm import tqdm
from pathlib import Path
import json
import time
import aiofiles
from gc import collect

class SyzbotGitCommit(BaseModel):
    """Git commit reference from Syzbot bug report.

    Attributes:
        title: Commit title/summary
        link: URL to commit view (optional)
        hashValue: Git commit SHA hash (optional)
        repo: Repository URL (optional)
        branch: Git branch name (optional)
    """
    model_config = ConfigDict(extra='allow', validate_by_alias=True, validate_by_name=True)

    title: str
    link: str | None=None
    hashValue: str | None=Field(default=None, validation_alias='hash')
    repo: str | None=None
    branch: str | None=None

class SyzbotCrash(BaseModel):
    """Single crash instance from a Syzbot bug report.

    Contains all information about a specific crash occurrence including
    reproducers, kernel configuration, and environment details.

    Attributes:
        title: Crash title/description
        syzReproducerLink: URL to syzkaller log reproducer
        syzReproducer: Content of syzkaller log reproducer
        cReproducerLink: URL to C reproducer
        cReproducer: Content of C reproducer
        kernelConfigLink: URL to kernel config
        kernelConfig: Content of kernel config
        kernelSourceGit: Git repository URL
        kernelSourceCommit: Git commit SHA where crash occurred
        syzkallerGit: Syzkaller repository URL
        syzkallerCommit: Syzkaller commit SHA used for fuzzing
        compilerDescription: Compiler version string
        architecture: CPU architecture (amd64, arm64, etc.)
        crashReportLink: URL to crash report
        fixedCReproducer: Fixed C reproducer (if available)
    """
    model_config = ConfigDict(extra='allow', validate_by_alias=True, validate_by_name=True)

    title: str=''
    syzReproducerLink: str | None=Field(default=None, validation_alias='syz-reproducer')
    syzReproducer: str | None=Field(default=None, validation_alias='syz-reproducer-data')
    cReproducerLink: str | None=Field(default=None, validation_alias='c-reproducer')
    cReproducer: str | None=Field(default=None, validation_alias='c-reproducer-data')
    kernelConfigLink: str=Field(validation_alias='kernel-config')
    kernelConfig: str | None=Field(default=None, validation_alias='kernel-config-data')
    kernelSourceGit: str=Field(default='', validation_alias='kernel-source-git')
    kernelSourceCommit: str=Field(validation_alias='kernel-source-commit')
    syzkallerGit: str=Field(validation_alias='syzkaller-git')
    syzkallerCommit: str=Field(validation_alias='syzkaller-commit')
    compilerDescription: str=Field(default='', validation_alias='compiler-description')
    architecture: str='amd64'
    crashReportLink: str | None=Field(default=None, validation_alias='crash-report-link')
    fixedCReproducer: str | None=Field(default=None, validation_alias='fixed-c-reproducer-data')

class SyzbotData(BaseModel):
    """Complete Syzbot bug report with all associated data.

    This model represents a full bug report from Syzbot including fix/cause commits,
    crash instances, reproducers, patches, and enriched metadata from git repositories.

    Attributes:
        version: Data format version
        title: Bug title
        displayTitle: Display-friendly title
        bugId: Unique bug identifier
        status: Bug status (open, fixed, etc.)
        fixCommits: List of commits that fix the bug
        causeCommit: Commit that introduced the bug
        discussions: URLs to related discussions
        crashes: List of crash instances with reproducers
        patchModifiedFunctions: Functions modified by fix patch
        patchCommitDate: Date of fix commit
        causeCommitDate: Date of cause commit
        subsystems: Affected kernel subsystems
        parentOfFixCommit: Parent commit SHA of fix
        patch: Full patch text
        patchMessage: Patch commit message
        patchModifiedFiles: Files modified by patch
        rawCrashReport: Raw crash report text
        cleanCrashReport: Parsed crash report
        crashKernelId: Kernel identifier
        causeModifiedFunctions: Functions modified by cause commit
        userspaceImage: Userspace image to use for reproduction
    """
    model_config = ConfigDict(extra='allow', validate_by_alias=True, validate_by_name=True)

    version: int=1
    title: str
    displayTitle: str=Field(default="", validation_alias='display-title')
    bugId: str=Field(validation_alias='id')
    status: str
    fixCommits: List[SyzbotGitCommit]=Field(default=[], validation_alias='fix-commits')
    causeCommit: SyzbotGitCommit | None=Field(default=None, validation_alias='cause-commit')
    discussions: List[str]=[]
    crashes: List[SyzbotCrash]=[]
    patchModifiedFunctions: List[List[str]] | None=Field(default=None, validation_alias='patch_modified_functions')
    patchCommitDate: datetime | None=Field(default=None, validation_alias='patch_commit_date')
    causeCommitDate: datetime | None=Field(default=None, validation_alias='cause_commit_date')
    subsystems: List[str] | None=None
    parentOfFixCommit: str | None=Field(default=None, validation_alias='parent_of_fix_commit')
    patch: str | None=Field(default=None)
    patchMessage: str | None=Field(default=None)
    patchModifiedFiles: List[str] | None=Field(default=None, validation_alias='patch_modified_files')
    rawCrashReport: str | None=Field(default=None, validation_alias='raw_crash_report')
    cleanCrashReport: List[List[Dict[str, Any]]] | None=Field(default=None, validation_alias='clean_crash_report')
    crashKernelId: str | None=Field(default=None, validation_alias='crash_kernel_id')
    causeModifiedFunctions: List[List[str]] | None=Field(default=None, validation_alias='cause_modified_functions')
    userspaceImage: str | None=Field(default='buildroot.raw')

class SyzbotDataset(RootModel):
    """Collection of Syzbot bug reports.

    A container for multiple SyzbotData instances, providing convenient
    access and serialization for datasets.

    Attributes:
        root: List of SyzbotData bug reports

    Example:
        >>> dataset = SyzbotDataset(root=[bug1, bug2, bug3])
        >>> for bug in dataset.root:
        ...     print(f"{bug.bugId}: {bug.title}")
    """
    root: List[SyzbotData]

    @classmethod
    def from_hf(cls, repository: str, config: str):
        """Load dataset from Hugging Face Hub.

        Args:
            repository: Hugging Face repository name
            config: Dataset configuration name

        Returns:
            SyzbotDataset loaded from HF

        Example:
            >>> dataset = SyzbotDataset.from_hf("org/repo", "default")
        """
        from datasets import load_dataset
        return cls.model_validate(load_dataset(repository, config)['train'])

    def get(self, bug_id: str) -> SyzbotData | None:
        ret = list(filter(lambda x: x.bugId == bug_id, self.root))
        if len(ret) > 0:
            return ret[0]

class SyzbotDriver:
    def __init__(self):
        from aiolimiter import AsyncLimiter
        self._session = requests.Session()
        self._session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.7727.102 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
            'Accept-Language': 'zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7',
            'sec-ch-ua': '"Google Chrome";v="147", "Not.A/Brand";v="8", "Chromium";v="147"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"macOS"',
        })
        self._syzbot_url = 'https://syzkaller.appspot.com'
        self._limiter = AsyncLimiter(8, 15)

        # Initialize cache
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._cache_loaded = False
        cache_dir = Path.home() / '.kgym_cache'
        cache_dir.mkdir(exist_ok=True)
        self._cache_file = cache_dir / f'{self.__class__.__name__}.json'

    async def _load_cache(self):
        """Load cache from disk if it exists."""
        if self._cache_loaded:
            return

        if self._cache_file.exists():
            try:
                async with aiofiles.open(self._cache_file, 'r') as f:
                    content = await f.read()
                    self._cache = json.loads(content)
            except (json.JSONDecodeError, IOError):
                # If cache file is corrupted, start with empty cache
                self._cache = {}

        self._cache_loaded = True

    async def _save_cache(self):
        """Save cache to disk asynchronously."""
        try:
            async with aiofiles.open(self._cache_file, 'w') as f:
                await f.write(json.dumps(self._cache, indent=2))
        except IOError:
            # Silently ignore write errors
            pass

    async def _sess_get(self, ttl: int = 2**64, **kwargs) -> requests.Response:
        """Fetch URL with optional caching.

        Args:
            ttl: Time-to-live in seconds. If > 0, cache the response.
                 If 0, always fetch fresh data.
            **kwargs: Arguments passed to requests.Session.get()

        Returns:
            requests.Response object
        """
        # Load cache if not already loaded
        await self._load_cache()

        url = kwargs.get('url', '')

        # Check cache if TTL is specified
        if ttl > 0 and url in self._cache:
            cached_entry = self._cache[url]
            retrieved_time = cached_entry.get('retrieved_time', 0)
            current_time = time.time()

            # If cache is still valid, return cached response
            if current_time - retrieved_time < ttl and cached_entry.get('status_code', 429) == 200:
                # Create a mock response object with cached content
                response = requests.Response()
                response._content = cached_entry['content'].encode('utf-8')
                response.status_code = cached_entry.get('status_code', 200)
                response.headers.update(cached_entry.get('headers', {}))
                response.url = url
                return response

        response = None
        # Fetch from network
        for _ in range(3):
            async with self._limiter:
                response = await run_async(self._session.get, **kwargs)
            if response.status_code != 200:
                await asyncio.sleep(2)
                continue
            else:
                break

        # Update cache always;
        self._cache[url] = {
            'content': response.text,
            'retrieved_time': time.time(),
            'status_code': response.status_code,
            'headers': dict(response.headers)
        }
        await self._save_cache()

        return response

class SyzbotPopulator(SyzbotDriver):

    def __init__(
        self,
        repository_map: dict[str, str]
    ):
        super().__init__()
        self.repository_map = repository_map
        self._fetch_sem = asyncio.Semaphore(4)

    async def fetch_orphan(self, repo_path: str, commit_id: str):
        code = await ((await asp.create_subprocess_exec(
            'git',
            'cat-file',
            '-e',
            commit_id,
            cwd=repo_path,
            stdin=asp.DEVNULL)).wait())
        if code != 0:
            return await ((await asp.create_subprocess_exec(
                'git',
                'fetch',
                'origin',
                f'{commit_id}:refs/remotes/origin/orphaned-commits/{commit_id}',
                cwd=repo_path,
                stdin=asp.DEVNULL)).wait())
        else:
            return 0

    async def _populate_syzbot_info(self, data: SyzbotData):
        async with self._fetch_sem:
            if data.crashes and len(data.crashes) > 0:
                data.crashes = data.crashes[:1]
                crash = data.crashes[0]
                if crash.kernelConfigLink and not crash.kernelConfig:
                    crash.kernelConfig = (await self._sess_get(
                        url=self._syzbot_url + crash.kernelConfigLink
                    )).text
                if crash.cReproducerLink and not crash.cReproducer:
                    crash.cReproducer = (await self._sess_get(
                        url=self._syzbot_url + crash.cReproducerLink
                    )).text
                if crash.syzReproducerLink and not crash.syzReproducer:
                    crash.syzReproducer = (await self._sess_get(
                        url=self._syzbot_url + crash.syzReproducerLink
                    )).text
                if crash.crashReportLink and not data.rawCrashReport:
                    data.rawCrashReport = (await self._sess_get(
                        url=self._syzbot_url + crash.crashReportLink
                    )).text

    async def _fetch_commits(self, repo_path: str, commits: List[str]):
        async with self._fetch_sem:
            for cmt in commits:
                await self.fetch_orphan(repo_path, cmt)

    async def get_repository_urls(self, batch: List[SyzbotData]) -> List[str]:
        ret = set()
        for data in batch:
            # fixCommits;
            if data.fixCommits and len(data.fixCommits) > 0:
                cmt = data.fixCommits[0]
                if not cmt.link or not cmt.hashValue:
                    continue
                git_url = kBuilderArgument.parse_url(cmt.link)
                ret.add(git_url)
            # causeCommit;
            if data.causeCommit:
                cmt = data.causeCommit
                if not cmt.link or not cmt.hashValue:
                    continue
                git_url = kBuilderArgument.parse_url(cmt.link)
                ret.add(git_url)
        return list(ret)

    async def get_diff(self, checkout_path: str, commit_bef, commit_aft):
        proc = await asp.create_subprocess_exec('git', 'diff', commit_bef, commit_aft, stderr=asp.DEVNULL, stdin=asp.DEVNULL, stdout=asp.PIPE, cwd=checkout_path)
        return (await proc.communicate())[0].decode()

    async def populate_batch(self, _batch: SyzbotDataset) -> SyzbotDataset:
        batch = deepcopy(_batch).root

        async with asyncio.TaskGroup() as tg:
            for data in batch:
                tg.create_task(self._populate_syzbot_info(data))

        commits_to_load = defaultdict(list)
        commits = dict[str, Commit]()

        for data in batch:
            from ..kclient_models.kbuilder import kBuilderArgument
            # fixCommits;
            if data.fixCommits and len(data.fixCommits) > 0:
                cmt = data.fixCommits[0]
                if not cmt.link or not cmt.hashValue:
                    continue
                git_url = kBuilderArgument.parse_url(cmt.link)
                if git_url in self.repository_map:
                    commit_id = cmt.hashValue
                    commits_to_load[git_url].append(commit_id)
            # causeCommit;
            if data.causeCommit:
                cmt = data.causeCommit
                if not cmt.link or not cmt.hashValue:
                    continue
                git_url = kBuilderArgument.parse_url(cmt.link)
                if git_url in self.repository_map:
                    commit_id = cmt.hashValue
                    commits_to_load[git_url].append(commit_id)

        fetch_tasks = []
        for git_url in commits_to_load:
            fetch_tasks.append(asyncio.create_task(self._fetch_commits(
                self.repository_map[git_url], commits_to_load[git_url]
            )))
        if len(fetch_tasks) > 0:
            await asyncio.wait(fetch_tasks)

        def _populate_commits():
            for git_url in commits_to_load:
                local_repo_path = self.repository_map[git_url]
                repo = Repository(path_to_repo=local_repo_path, only_commits=commits_to_load[git_url], include_refs=True)
                for cmt in repo.traverse_commits():
                    commits[cmt.hash] = cmt
        await run_async(_populate_commits)

        for data in batch:
            from ..kclient_models.kbuilder import kBuilderArgument
            # fixCommits;
            if data.fixCommits and len(data.fixCommits) > 0:
                cmt = data.fixCommits[0]
                if not cmt.link or not cmt.hashValue:
                    continue
                git_url = kBuilderArgument.parse_url(cmt.link)
                if git_url not in self.repository_map:
                    continue
                commit = commits[cmt.hashValue]

                if len(commit.parents) > 0:
                    data.parentOfFixCommit = commit.parents[0]
                data.patchCommitDate = (commit.committer_date - commit.committer_date.utcoffset()).replace(tzinfo=None)
                data.patchMessage = commit.msg
                data.patchModifiedFunctions = []
                data.patchModifiedFiles = []
                data.patch = await self.get_diff(self.repository_map[git_url], data.parentOfFixCommit, cmt.hashValue)
                for m in commit.modified_files:
                    data.patchModifiedFunctions.append([x.name for x in m.changed_methods])
                    data.patchModifiedFiles.append(m.old_path)

            # causeCommit;
            if data.causeCommit:
                cmt = data.causeCommit
                if not cmt.link or not cmt.hashValue:
                    continue
                git_url = kBuilderArgument.parse_url(cmt.link)
                if git_url not in self.repository_map:
                    continue
                commit = commits[cmt.hashValue]
                data.causeCommitDate = (commit.committer_date - commit.committer_date.utcoffset()).replace(tzinfo=None)
                data.causeModifiedFunctions = []
                for m in commit.modified_files:
                    data.causeModifiedFunctions.append([x.name for x in m.changed_methods])

        return SyzbotDataset(root=batch)

class SyzbotCrawler(SyzbotDriver):

    def __init__(self, max_reported_days: int=-1):
        super().__init__()
        self._max_reported_days = max_reported_days

    async def _crawl(self, bug_type: Literal['fixed', 'open'], url: str) -> SyzbotData:
        d = from_json((await self._sess_get(url=url + '&json=1')).text)
        d['status'] = bug_type
        return SyzbotData.model_validate(d)

    async def crawl_id(self, bug_type: Literal['fixed', 'open'], id: str) -> SyzbotData:
        return await self._crawl(bug_type, self._syzbot_url + '/bug?id=' + id)

    async def crawl_extid(self, bug_type: Literal['fixed', 'open'], extid: str) -> SyzbotData:
        return await self._crawl(bug_type, self._syzbot_url + '/bug?extid=' + extid)

    async def _get(self, delimiter: str, thead, tbody) -> list[str]:
        title_idx, repro_idx, report_idx = 0, 0, 0
        for i, th in enumerate(thead):
            txt = th.xpath('a')[0].text
            if txt == 'Title':
                title_idx = i
            if txt == 'Repro':
                repro_idx = i
            if txt == 'Reported':
                report_idx = i
        ret = []
        for row in tbody:
            a = row.xpath('td')[title_idx].xpath('a')[0]
            href = a.get('href')
            repro = row.xpath('td')[repro_idx].text
            if repro == '' or repro is None:
                continue
            reported = row.xpath('td')[report_idx].xpath('a')
            if len(reported) == 0:
                continue
            reported = reported[0].text
            reported_days = 1
            if reported == 'now':
                reported_days = 0
            elif 'd' in reported:
                reported_days = int(reported.split('d')[0])
            else:
                reported_days = 1
            if self._max_reported_days != -1 and reported_days > self._max_reported_days:
                continue
            if href.find(delimiter) == -1:
                continue
            _id = href.split(f'?{delimiter}=')[1]
            subsystems = []
            spans = row.xpath('td')[title_idx].xpath('span')
            for span in spans:
                subsystems.append(span.xpath('a')[0].text)
            ret.append((_id, reported_days, subsystems))
        return ret

    async def get_extids(self, thead, tbody):
        return await self._get('extid', thead, tbody)
    
    async def get_ids(self, thead, tbody):
        return await self._get('id', thead, tbody)

    async def crawl_open_table(self):
        tr = fromstring((await self._sess_get(
            url=self._syzbot_url + '/upstream',
            ttl=0
        )).text)
        fa = tr.xpath("//details")[0].xpath('table')[0]
        thead = fa.xpath('thead/tr')[0]
        tbody = fa.xpath('tbody')[0]
        return await self.get_extids(thead, tbody)

    async def crawl_fixed_table(self):
        tr = fromstring((await self._sess_get(
            url=self._syzbot_url + '/upstream/fixed',
            ttl=0
        )).text)
        fa = tr.xpath("//table[@class='list_table']")[0]
        thead = fa.xpath('thead/tr')[0]
        tbody = fa.xpath('tbody')[0]
        return await self.get_extids(thead, tbody)

# kCache;

kCacheIndex = RootModel[Dict[str, Union[JobId, JobResource]]]

class EvaluationResult(BaseModel):
    jobId: JobId
    jobContext: kJobContext
    status: JobStatus
    evaluation: Literal['notReproduced', 'reproduced', 'compilationError', 'imageError', 'error']
    image: Literal['normal', 'warning', 'error'] | None = None
    title: str | None = None
    resources: CrashIncident | None = None

kBenchEvaluationResult = RootModel[Dict[str, EvaluationResult]]

class LLMEvaluationResult(BaseModel):
    prompt: str
    yes: int
    no: int
    llmError: int
    result: Literal['yes', 'no']
    replies: List[str]

LLMEvaluationResults = RootModel[Dict[str, LLMEvaluationResult]]

class kBench(BaseModel):
    """Benchmark for evaluating kernel crash reproduction.

    Combines a Syzbot dataset with pre-built kernel caches to enable
    efficient crash reproduction evaluation. Provides methods for running
    benchmarks, collecting results, and evaluating with LLM judges.

    Attributes:
        dataset: Collection of Syzbot bug reports
        kCache: Mapping from bug IDs to pre-built kernel JobResource or JobId

    Example:
        Building and running a benchmark:

        >>> # Build benchmark from dataset
        >>> async with kGymAsyncClient("http://localhost:8000") as client:
        ...     bench = await kBench.build(
        ...         client,
        ...         dataset,
        ...         timeout=3600
        ...     )
        ...     # Save benchmark
        ...     with open("bench.json", "w") as f:
        ...         f.write(bench.model_dump_json())
        ...
        ...     # Evaluate benchmark
        ...     results = await bench.evaluate_kgym(
        ...         client,
        ...         patches={"bug1": "patch content..."},
        ...         timeout=3600
        ...     )
    """
    dataset: SyzbotDataset
    kCache: kCacheIndex

    model_config = ConfigDict(extra='allow')

    @classmethod
    def load(cls, path: str) -> 'kBench':
        """Load benchmark from JSON file.

        Args:
            path: Path to JSON file containing benchmark

        Returns:
            Loaded kBench instance

        Example:
            >>> bench = kBench.load("benchmark.json")
        """
        with open(path, 'r') as fp:
            return kBench.model_validate_json(fp.read())

    async def evaluate_llm_judge(
        self,
        model_name: str,
        router: litellm.Router,
        patches: dict[str, str] | None=None,
        temperature: float=0.8,
        reasoning_effort: str='medium',
        n_vote: int=5,
        n_worker: int=16,
        only_bug_ids: list[str] | None=None,
        pbar: bool=True
    ) -> LLMEvaluationResults:
        from concurrent.futures import ThreadPoolExecutor
        from functools import partial
        loop = asyncio.get_running_loop()
        execPool = ThreadPoolExecutor(max_workers=n_worker)

        pgbar = None

        async def _eval_llm(bugId: str):
            patch = patches[bugId]
            bug = list(filter(lambda x: x.bugId == bugId, self.dataset.root))[0]
            ret = LLMEvaluationResult(
                prompt=f"""Now, there is a kernel crash, and a student has come up with a patch for the crash.
However, there has been already a ground truth patch approved and merged into Linux. In order to give feedback to the student,
you are required to review both student's patch and ground truth patch.

Peer's patch:
<peer patch>
{patch}
</peer patch>

<approved patch>
{bug.patchMessage}

```
{bug.patch}
```
</approved patch>

The approved patch is absolutely correct because it has been reviewed by multiple kernel maintainers.

Now, you have read the patches. Please tell us if the student's patch does the EXACT SAME THING as the ground truth patch, and reason the verdict you make.
In order to have a sound verdict, you should analyze the behavior of both patch, and compare the analyzed behavior. It is OK to have different variable names.
Any implementations of other kinds of behaviors should be rejected.
Respond in the following format:
```
<ground truth patch analysis>...</ground truth patch analysis>
<student's patch analysis>...</student's patch analysis>
<verdict>same|different</verdict>
```
Make sure you follow the format!""",
                yes=0,
                no=0,
                llmError=0,
                result='no',
                replies=[]
            )
            resps = []
            for _ in range(n_vote):
                resps.append(await loop.run_in_executor(execPool, partial(router.completion,
                    model=model_name,
                    messages=[
                        { "role": "system", "content": "You are a kernel expert." },
                        { "role": "user", "content": ret.prompt }
                    ],
                    reasoning_effort=reasoning_effort,
                    temperature=temperature
                )))
                if pbar:
                    pgbar.update(1)
            for r in resps:
                choice = r.choices[0]
                ret.replies.append(choice.message.content)
                if '<verdict>same</verdict>' in choice.message.content:
                    ret.yes += 1
                elif '<verdict>different</verdict>' in choice.message.content:
                    ret.no += 1
                else:
                    ret.llmError += 1
            ret.result = 'yes' if ret.yes > ret.no + ret.llmError else 'no'
            return bugId, ret

        if pbar:
            total = 0
            for x in self.dataset.root:
                if only_bug_ids is None or x.bugId in only_bug_ids:
                    total += n_vote
            pgbar = tqdm(total=total)

        tasks = []
        for x in self.dataset.root:
            if only_bug_ids is None or x.bugId in only_bug_ids:
                tasks.append(asyncio.create_task(_eval_llm(x.bugId)))

        if len(tasks) > 0:
            await asyncio.wait(tasks)
        ret = {}
        for t in tasks:
            bug_id, e = t.result()
            ret[bug_id] = e
        return LLMEvaluationResults(root=ret)

    async def submit_kgym_evaluation(
        self,
        _client: 'kGymAsyncClient',
        patches: dict[str, str] | None=None,
        userspace_image: str | None=None,
        only_bug_ids: list[str] | None=None,
        pbar: bool=True,
        n_batch: int=1,
        **kwargs
    ) -> dict[str, JobId]:
        """Submit crash reproduction jobs for all bugs in benchmark.

        Creates and submits jobs to reproduce crashes, optionally applying
        patches before reproduction. Jobs use cached kernels from the benchmark.

        Args:
            _client: kGymAsyncClient instance
            patches: Dictionary mapping bug IDs to patch strings to apply
            userspace_image: Override userspace image name
            only_bug_ids: List of specific bug IDs to evaluate (None = all)
            pbar: Show progress bar
            **kwargs: Additional arguments passed to kVMManagerArgument

        Returns:
            Dictionary mapping bug IDs to submitted job IDs

        Example:
            >>> patches = {"bug1": "diff --git ...", "bug2": "diff --git ..."}
            >>> receipt = await bench.submit_kgym_evaluation(
            ...     client,
            ...     patches=patches,
            ...     only_bug_ids=["bug1", "bug2"]
            ... )
            >>> print(f"Submitted {len(receipt)} jobs")
        """
        from .kgym_client import kGymAsyncClient
        if patches is None:
            patches = dict()
        client: kGymAsyncClient = _client
        receipt = {}
        if pbar:
            print('Issuing evaluation jobs...')
        try:
            it = self.dataset.root
            if pbar:
                it = tqdm(it)
            for syzbot_data in it:
                if only_bug_ids and syzbot_data.bugId not in only_bug_ids:
                    continue

                if isinstance(self.kCache.root[syzbot_data.bugId], JobId):
                    cached_job_ctx = await client.get_job(self.kCache.root[syzbot_data.bugId])
                    cached_result: kBuilderResult = cached_job_ctx.jobWorkers[0].workerResult
                    kCache = cached_result.kCache
                else:
                    kCache = self.kCache.root[syzbot_data.bugId]

                patch = patches.get(syzbot_data.bugId, '')
                workers = []
                tags = dict()

                image: Image | int = 0
                try:
                    workers.append(kBuilderArgument(
                        kernelSource=kCache,
                        userspaceImage=syzbot_data.userspaceImage if userspace_image is None else userspace_image,
                        patch=patch
                    ))
                    image = 0
                    for _ in range(n_batch):
                        workers.append(kVMManagerArgument.model_from_syzbot_data(
                            syzbot_data=syzbot_data,
                            image=image,
                            **kwargs
                        ))
                    req = kJobRequest(
                        jobWorkers=workers,
                        tags=tags
                    )
                    receipt[syzbot_data.bugId] = await client.create_job(req)
                except Exception as e:
                    print('Error when running evaluation:')
                    from traceback import print_exc
                    print_exc()
            return receipt
        except KeyboardInterrupt:
            it = receipt
            if pbar:
                print('Aborting jobs...')
                it = tqdm(it) 
            for bug_id in it:
                await client.abort_job(receipt[bug_id])
            return None

    async def poll_kgym_evaluation(
        self,
        _client: 'kGymAsyncClient',
        receipt: dict[str, JobId],
        pbar: bool=True,
        timeout: int=-1
    ) -> kBenchEvaluationResult | None:
        from .kgym_client import kGymAsyncClient
        client: kGymAsyncClient = _client
        try:
            # poll;
            cnt = 0
            inc = 60 if timeout == -1 else min(timeout, 60)
            total = set(receipt.keys())
            successful_runs = set()
            unsuccessful_runs = set()
            prog_bar = None
            if pbar:
                print('Waiting for jobs to finish...')
                prog_bar = tqdm(total=len(total))
            while len(total) > 0 and (timeout == -1 or cnt < timeout):
                await asyncio.sleep(inc)
                cnt += inc
                # poll result;
                for bug_id in total:
                    job_id = receipt[bug_id]
                    ctx = await client.get_job(job_id)
                    if ctx.status == JobStatus.Finished:
                        successful_runs.add(bug_id)
                        if pbar:
                            prog_bar.update(1)
                    elif ctx.status == JobStatus.Aborted:
                        unsuccessful_runs.add(bug_id)
                        if pbar:
                            prog_bar.update(1)
                total = total.difference(successful_runs)
                total = total.difference(unsuccessful_runs)
        except KeyboardInterrupt:
            it = receipt
            if pbar:
                print('Aborting jobs...')
                it = tqdm(it) 
            for bug_id in it:
                await client.abort_job(receipt[bug_id])
            return None

        ret = dict[str, EvaluationResult]()
        for bug_id in receipt:
            job_id: JobId = receipt[bug_id]
            job_ctx = await client.get_job(job_id)
            er = EvaluationResult(
                jobId=str(job_id),
                jobContext=job_ctx,
                status=job_ctx.status,
                evaluation='error'
            )
            if job_ctx.status != JobStatus.Finished:
                if (
                    job_ctx.jobWorkers[0].workerResult.jobException and
                    job_ctx.jobWorkers[0].workerResult.jobException.code and
                    job_ctx.jobWorkers[0].workerResult.jobException.code in (
                        'kbuilder.KernelBuildError',
                        'kbuilder.PatchApplicationError'
                    )
                ):
                    er.evaluation = 'compilationError'
                ret[bug_id] = er
                continue
            results = list[kVMManagerResult]()
            for worker in job_ctx.jobWorkers:
                if worker.workerType == 'kvmmanager':
                    results.append(worker.workerResult)
            # result: kVMManagerResult = job_ctx.jobWorkers[-1].workerResult
            # check image ability first;
            er.image = 'error'
            for result in results:
                if result.imageAbility == 'normal':
                    er.image = 'normal'
                elif result.imageAbility == 'warning' and er.image != 'normal':
                    er.image = 'warning'
            if er.image == 'error':
                er.evaluation = 'imageError'
            else:
                er.evaluation = 'notReproduced'
                er.resources = None
                for result in results:
                    if result.crashes is None:
                        continue
                    found = False
                    for crash in result.crashes:
                        if crash.crashType == 'special':
                            continue
                        er.evaluation = 'reproduced'
                        er.title = crash.title
                        er.resources = crash.incidents[0]
                        found = True
                        break
                    if found:
                        break
            ret[bug_id] = er
        return kBenchEvaluationResult(root=ret)

    async def evaluate_kgym(
        self,
        _client: 'kGymAsyncClient',
        patches: dict[str, str] | None=None,
        timeout: int=-1,
        userspace_image: str | None=None,
        only_bug_ids: list[str] | None=None,
        pbar: bool=True,
        n_batch: int=1,
        **kwargs
    ) -> kBenchEvaluationResult | None:
        """Complete benchmark evaluation: submit jobs, wait, collect results.

        High-level method that handles the full evaluation workflow:
        1. Submits crash reproduction jobs (with optional patches)
        2. Polls for completion (with timeout)
        3. Collects and analyzes results

        Args:
            _client: kGymAsyncClient instance
            patches: Dictionary mapping bug IDs to patch strings
            timeout: Maximum wait time in seconds (-1 = unlimited)
            userspace_image: Override userspace image name
            only_bug_ids: Specific bug IDs to evaluate (None = all)
            pbar: Show progress bars
            **kwargs: Additional arguments for kVMManagerArgument

        Returns:
            kBenchEvaluationResult with per-bug evaluation outcomes,
            or None if interrupted

        Example:
            >>> # Evaluate untainted reproduction
            >>> results = await bench.evaluate_kgym(
            ...     client,
            ...     timeout=3600,
            ...     machineType="qemu:2-4096"
            ... )
            >>> for bug_id, result in results.root.items():
            ...     print(f"{bug_id}: {result.evaluation}")
            ...
            >>> # Evaluate with patches
            >>> patches = {"bug1": "patch text..."}
            >>> results = await bench.evaluate_kgym(
            ...     client,
            ...     patches=patches,
            ...     timeout=7200
            ... )
        """
        receipt = await self.submit_kgym_evaluation(
            _client,
            patches,
            userspace_image,
            only_bug_ids,
            pbar=pbar,
            n_batch=n_batch,
            **kwargs
        )
        if not receipt:
            return None
        for _ in range(10):
            try:
                return await self.poll_kgym_evaluation(
                    _client,
                    receipt,
                    pbar,
                    timeout
                )
            except:
                pass
        print('Exception occured when polling kGym')
        Path('./receipt.json').write_bytes(to_json(receipt, indent=4))
        print(f'Receipt saved as "./receipt.json".')
        from traceback import print_exc
        print_exc()

    @classmethod
    async def _poll_kcache_job(
        cls,
        _client: 'kGymAsyncClient',
        dataset: SyzbotDataset,
        kcache: kCacheIndex,
        timeout: int=-1
    ) -> Tuple[SyzbotDataset, kCacheIndex]:
        from .kgym_client import kGymAsyncClient
        kcache = deepcopy(kcache)
        client: kGymAsyncClient = _client

        cnt = 0
        inc = 60 if timeout == -1 else min(timeout, 60)

        total = set(kcache.root.keys())
        successful_runs = set()
        unsuccessful_runs = set()

        while len(total) > 0 and (timeout == -1 or cnt < timeout):
            await asyncio.sleep(inc)
            cnt += inc
            # poll result;
            for bug_id in total:
                job_id = kcache.root[bug_id]
                ctx = await client.get_job(job_id)
                if ctx.status == JobStatus.Finished:
                    successful_runs.add(bug_id)
                elif ctx.status == JobStatus.Aborted:
                    unsuccessful_runs.add(bug_id)
            total = total.difference(successful_runs)
            total = total.difference(unsuccessful_runs)

        # filter out;
        kcache = kcache.root
        bug_ids = list(kcache.keys())
        for bug_id in bug_ids:
            if bug_id not in successful_runs:
                del kcache[bug_id]
        dataset = SyzbotDataset(root=list(filter(
            lambda x: x.bugId in successful_runs,
            dataset.root
        )))
        return dataset, kCacheIndex(root=kcache)

    @classmethod
    async def build(
        cls,
        _client: 'kGymAsyncClient',
        dataset: SyzbotDataset,
        userspace_image_name: str | None=None,
        compiler: str='',
        linker: str='',
        crash_index: int = 0,
        commit_from: Literal['parent', 'crash']='parent',
        timeout: int=-1,
        **kwargs
    ) -> tuple['kBench', kBenchEvaluationResult, kCacheIndex]:
        """Build a benchmark from a Syzbot dataset.

        Creates pre-built kernel caches for all bugs in the dataset and
        performs initial reproducibility testing. Only bugs with reproducible
        crashes are included in the final benchmark.

        This is a multi-stage process:
        1. Build kernels for all bugs (using parent or crash commit)
        2. Wait for builds to complete
        3. Test crash reproducibility on built kernels
        4. Filter to only reproducible bugs

        Args:
            _client: kGymAsyncClient instance
            dataset: SyzbotDataset containing bug reports
            userspace_image_name: Userspace image for reproduction
            compiler: Compiler to use ('gcc' or 'clang', auto-detect if empty)
            linker: Linker to use ('ld' or 'ld.lld', auto-detect if empty)
            crash_index: Which crash from crashes list to use
            commit_from: Use 'parent' of fix or 'crash' commit for kernel
            timeout: Maximum wait time for operations (-1 = unlimited)
            **kwargs: Additional arguments for kVMManagerArgument

        Returns:
            kBench with pre-built caches and filtered reproducible bugs

        Example:
            >>> # Build benchmark from dataset
            >>> dataset = SyzbotDataset.from_hf("repo", "config")
            >>> async with kGymAsyncClient("http://localhost:8000") as client:
            ...     bench, eval_result = await kBench.build(
            ...         client,
            ...         dataset,
            ...         userspace_image_name="buildroot.raw",
            ...         compiler="gcc",
            ...         timeout=7200
            ...     )
            ...     # Save for later use
            ...     with open("benchmark.json", "w") as f:
            ...         f.write(bench.model_dump_json())
            ...     print(f"Built benchmark with {len(bench.dataset.root)} bugs")
        """
        from .models import kJobRequest
        from ..kclient_models.kbuilder import kBuilderArgument
        from .kgym_client import kGymAsyncClient

        dataset = deepcopy(dataset)
        client: kGymAsyncClient = _client
        ret = dict()
        try:
            for data in dataset.root:
                kbuilder_arg = kBuilderArgument.model_from_syzbot_data(
                    syzbot_data=data,
                    userspace_image_name=userspace_image_name,
                    compiler=compiler,
                    linker=linker,
                    crash_index=crash_index,
                    commit_from=commit_from
                )
                req = kJobRequest(
                    jobWorkers=[kbuilder_arg],
                    tags={
                        'bugId': data.bugId,
                        'kernelCommit': kbuilder_arg.kernelSource.commitId
                    }
                )
                ret[data.bugId] = await client.create_job(req)
            kcache_crude = kCacheIndex(root=ret)
            dataset, kcache = await cls._poll_kcache_job(
                _client=client,
                dataset=dataset,
                kcache=kcache_crude,
                timeout=timeout
            )
            kcache_failed = {}
            for bug_id in kcache_crude.root:
                if bug_id not in kcache.root:
                    kcache_failed[bug_id] = kcache_crude.root[bug_id]

            # filtered out uncompilable builds;
            # now, do reproducibility test;
            preliminary_bench = kBench(
                dataset=dataset,
                kCache=kcache
            )
            eval_result = await preliminary_bench.evaluate_kgym(client, timeout=timeout, userspace_image=userspace_image_name, **kwargs)
            return kBench(
                dataset=preliminary_bench.dataset.root,
                kCache=preliminary_bench.kCache
            ), eval_result, kCacheIndex(root=kcache_failed)
        except KeyboardInterrupt:
            print('Aborting jobs...')
            for bug_id in tqdm(ret):
                await client.abort_job(ret[bug_id])
            return
