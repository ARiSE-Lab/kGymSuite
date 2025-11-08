import subprocess as sp
import os, json
from hashlib import md5

urls = ['https://git.kernel.org/pub/scm/linux/kernel/git/bpf/bpf.git',
    'https://git.kernel.org/pub/scm/linux/kernel/git/davem/net.git',
    'https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git',
    'https://git.kernel.org/pub/scm/linux/kernel/git/bpf/bpf-next.git',
    'https://git.kernel.org/pub/scm/linux/kernel/git/davem/net-next.git',
    'https://git.kernel.org/pub/scm/linux/kernel/git/next/linux-next.git'
]

if __name__ == '__main__':
    procs = list[sp.Popen]()
    ret = {}
    cwd = os.path.dirname(__file__)
    for url in urls:
        name = md5(url.encode('utf-8')).hexdigest()
        procs.append(sp.Popen([
            'git', 'clone', '--bare',
            url, f'./{name}.git'
        ], stdout=sp.DEVNULL, stdin=sp.DEVNULL, cwd=cwd))
        ret[url] = os.path.abspath(os.path.join(cwd, f'./{name}.git'))

    with open(os.path.join(cwd, 'map.json'), 'w') as fp:
        json.dump(ret, fp)

    while len(procs) > 0:
        procs[0].wait()
        procs = procs[1:]
