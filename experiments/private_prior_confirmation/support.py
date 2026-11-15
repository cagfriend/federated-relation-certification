"""Experiment identity and atomic records, independent of historical drivers."""
import ast
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]


def read(path):
    return json.loads(Path(path).read_bytes())


def digest(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(2**20),b''):
            h.update(block)
    return h.hexdigest()


def seal(record):
    record.pop('run_sha256',None)
    record['run_sha256']=hashlib.sha256(json.dumps(record,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
    return record


def write(path,record):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_suffix(path.suffix+'.part')
    temporary.write_text(json.dumps(record,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    temporary.replace(path)


def sources():
    found={}
    def visit(module):
        path=ROOT.joinpath(*module.split('.')).with_suffix('.py')
        if not path.is_file():
            path=ROOT.joinpath(*module.split('.'))/'__init__.py'
        if not path.is_file() or path.relative_to(ROOT).as_posix() in found:
            return
        found[path.relative_to(ROOT).as_posix()]=digest(path)
        package=module.split('.') if path.name=='__init__.py' else module.split('.')[:-1]
        for node in ast.walk(ast.parse(path.read_text(encoding='utf-8-sig'))):
            if isinstance(node,ast.Import):
                for item in node.names:
                    if item.name.startswith('experiments.'):visit(item.name)
            elif isinstance(node,ast.ImportFrom):
                base=node.module or ''
                if node.level:
                    base='.'.join(package[:len(package)-node.level+1]+([base] if base else []))
                if base.startswith('experiments'):
                    visit(base)
                    for item in node.names:visit(base+'.'+item.name)
    for p in Path(__file__).parent.glob('*.py'):
        if not p.name.startswith('test_'):
            visit('experiments.private_prior_confirmation.'+p.stem)
    p=Path(__file__).parent/'PREREGISTRATION.md'
    found[p.relative_to(ROOT).as_posix()]=digest(p)
    return found
