from pathlib import Path
import ast,json,hashlib
ROOT=Path(__file__).resolve().parents[2]
def function(path,name):
 tree=ast.parse(path.read_text(encoding='utf-8'))
 return next(x for x in tree.body if isinstance(x,(ast.FunctionDef,ast.AsyncFunctionDef)) and x.name==name)
old=function(ROOT/'experiments/stl10_transfer/data.py','prepare')
new=function(ROOT/'experiments/quantity_heterogeneity/data.py','prepare')
def loop(f):return next(x for x in f.body if isinstance(x,ast.For) and isinstance(x.target,ast.Tuple) and any(isinstance(y,ast.Name) and y.id=='client' for y in ast.walk(x.target)))
assert ast.dump(loop(old),include_attributes=False)==ast.dump(loop(new),include_attributes=False),'AE/KMeans/feature preparation loop changed'
def public(f):return next(x for x in f.body if isinstance(x,ast.Assign) and any(isinstance(y,ast.Name) and y.id=='public_ids' for y in x.targets))
assert ast.dump(public(old),include_attributes=False)==ast.dump(public(new),include_attributes=False),'Public sampling stream changed'
env=json.loads((ROOT/'experiments/lr_client_scaling/results_full_fixed_per_client/environment.json').read_text(encoding='utf-8'))
for path,h in env['sources'].items():assert hashlib.sha256((ROOT/path).read_bytes()).hexdigest()==h,path
print(json.dumps(dict(AE_KMeans_feature_loop_identical=True,public_sampling_identical=True,old_frozen_sources_unchanged=len(env['sources']))))
