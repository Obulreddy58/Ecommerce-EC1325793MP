from pathlib import Path
import yaml

root = Path(__file__).resolve().parent.parent / 'kubernetes'
for service_dir in sorted(root.iterdir()):
    if not service_dir.is_dir():
        continue
    deploy_path = service_dir / 'deploy.yaml'
    if not deploy_path.exists():
        continue
    text = deploy_path.read_text(encoding='utf-8')
    docs = list(yaml.safe_load_all(text))
    if not docs:
        continue
    doc = docs[0]
    if not isinstance(doc, dict):
        continue
    kind = doc.get('kind', '')
    if kind != 'Rollout':
        continue
    spec = doc.get('spec', {})
    strategy = spec.get('strategy', {})
    if isinstance(strategy, dict) and 'canary' in strategy:
        canary = strategy['canary']
        rolling = {
            'type': 'RollingUpdate',
            'rollingUpdate': {
                'maxUnavailable': canary.get('maxUnavailable', 0),
                'maxSurge': canary.get('maxSurge', '25%')
            }
        }
        spec['strategy'] = rolling
        doc['spec'] = spec
    doc['apiVersion'] = 'apps/v1'
    doc['kind'] = 'Deployment'
    # Write out the converted deployment preserving only the first document.
    out = yaml.safe_dump(doc, sort_keys=False)
    deploy_path.write_text(out, encoding='utf-8')
    print(f'Converted {deploy_path}')

print('Conversion complete.')
