from pathlib import Path
import shutil
import yaml

repo_root = Path(__file__).resolve().parent.parent
k8s_root = repo_root / 'kubernetes'
helm_root = repo_root / 'helm'

DEPLOYMENT_TEMPLATE = '''apiVersion: apps/v1
kind: Deployment
metadata:
  name: {{ .Values.name }}
  labels:
{{ toYaml .Values.templateLabels | indent 2 }}
spec:
  replicas: {{ .Values.replicaCount }}
  selector:
    matchLabels:
{{ toYaml .Values.selectorLabels | indent 6 }}
  template:
    metadata:
      labels:
{{ toYaml .Values.templateLabels | indent 8 }}
    spec:
      serviceAccountName: {{ .Values.serviceAccountName | quote }}
      containers:
      - name: {{ .Values.service.name | quote }}
        image: "{{ .Values.image.repository }}:{{ .Values.image.tag }}"
        imagePullPolicy: {{ .Values.image.pullPolicy }}
        ports:
        - containerPort: {{ .Values.service.port }}
          name: service
        {{- if .Values.env }}
        env:
{{ toYaml .Values.env | indent 10 }}
        {{- end }}
        {{- if .Values.readinessProbe }}
        readinessProbe:
{{ toYaml .Values.readinessProbe | indent 10 }}
        {{- end }}
        {{- if .Values.livenessProbe }}
        livenessProbe:
{{ toYaml .Values.livenessProbe | indent 10 }}
        {{- end }}
        resources:
{{ toYaml .Values.resources | indent 10 }}
        {{- if .Values.volumeMounts }}
        volumeMounts:
{{ toYaml .Values.volumeMounts | indent 10 }}
        {{- end }}
      {{- if .Values.initContainers }}
      initContainers:
{{ toYaml .Values.initContainers | indent 8 }}
      {{- end }}
      {{- if .Values.volumes }}
      volumes:
{{ toYaml .Values.volumes | indent 8 }}
      {{- end }}
'''

SERVICE_TEMPLATE = '''apiVersion: v1
kind: Service
metadata:
  name: {{ .Values.name }}
  labels:
{{ toYaml .Values.templateLabels | indent 2 }}
spec:
  type: {{ .Values.service.type }}
  selector:
{{ toYaml .Values.selectorLabels | indent 4 }}
  ports:
  - name: service
    protocol: TCP
    port: {{ .Values.service.port }}
    targetPort: {{ .Values.service.targetPort }}
'''

INGRESS_TEMPLATE = '''{{- if .Values.ingress.enabled }}
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: {{ .Values.ingress.name | default .Values.name }}
  labels:
{{ toYaml .Values.templateLabels | indent 2 }}
  annotations:
{{ toYaml .Values.ingress.annotations | indent 4 }}
spec:
{{ toYaml .Values.ingress.spec | indent 2 }}
{{- end }}
'''

CONFIGMAP_TEMPLATE = '''{{- if .Values.configMaps }}
{{- range $index, $cm := .Values.configMaps }}
apiVersion: v1
kind: ConfigMap
metadata:
  name: {{ $cm.name }}
  labels:
{{ toYaml $.Values.templateLabels | indent 2 }}
data:
{{ toYaml $cm.data | indent 2 }}
---
{{- end }}
{{- end }}
'''

COMMON_NAMESPACE_TEMPLATE = '''apiVersion: v1
kind: Namespace
metadata:
  name: {{ .Values.namespace.name }}
  labels:
{{ toYaml .Values.namespace.labels | indent 2 }}
'''

COMMON_SERVICEACCOUNT_TEMPLATE = '''apiVersion: v1
kind: ServiceAccount
metadata:
  name: {{ .Values.serviceAccount.name }}
  labels:
{{ toYaml .Values.serviceAccount.labels | indent 2 }}
'''

COMMON_PDB_TEMPLATE = '''{{- range .Values.pdbs }}
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: {{ .name }}
  labels:
{{ toYaml .labels | indent 2 }}
spec:
  minAvailable: {{ .minAvailable }}
  selector:
{{ toYaml .selector | indent 4 }}
---
{{- end }}
'''

COMMON_HPA_TEMPLATE = '''{{- range .Values.hpas }}
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: {{ .name }}
  labels:
{{ toYaml .labels | indent 2 }}
spec:
  scaleTargetRef:
    apiVersion: {{ .scaleTargetRef.apiVersion }}
    kind: {{ .scaleTargetRef.kind }}
    name: {{ .scaleTargetRef.name }}
  minReplicas: {{ .minReplicas }}
  maxReplicas: {{ .maxReplicas }}
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: {{ .targetCPUUtilizationPercentage }}
---
{{- end }}
'''

COMMON_NETWORKPOLICY_TEMPLATE = '''apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: {{ .Values.networkPolicy.name }}
  labels:
{{ toYaml .Values.networkPolicy.labels | indent 2 }}
spec:
  podSelector:
    matchLabels: {{ toYaml .Values.networkPolicy.podSelector.matchLabels | indent 4 }}
  policyTypes:
  - Ingress
  ingress:
  - from:
    - namespaceSelector:
{{ toYaml .Values.networkPolicy.namespaceSelector | indent 6 }}
'''


def safe_load_all_yaml(path: Path):
    if not path.exists():
        return []
    return [doc for doc in yaml.safe_load_all(path.read_text(encoding='utf-8')) if doc]


def safe_load_yaml(path: Path):
    docs = safe_load_all_yaml(path)
    return docs[0] if docs else {}


def yaml_dump(data):
    return yaml.dump(data, sort_keys=False, default_flow_style=False)


def write_chart(chart_name: str, app_version: str, values: dict, templates: dict):
    chart_root = helm_root / chart_name
    chart_root.mkdir(parents=True, exist_ok=True)
    (chart_root / 'templates').mkdir(exist_ok=True)
    chart_yaml = {
        'apiVersion': 'v2',
        'name': chart_name,
        'description': f'Helm chart for {chart_name}',
        'type': 'application',
        'version': '0.1.0',
        'appVersion': app_version,
    }
    (chart_root / 'Chart.yaml').write_text(yaml_dump(chart_yaml), encoding='utf-8')
    (chart_root / 'values.yaml').write_text(yaml_dump(values), encoding='utf-8')
    for filename, content in templates.items():
        (chart_root / 'templates' / filename).write_text(content, encoding='utf-8')


def get_first_service_file(service_dir: Path):
    for name in ['svc.yaml', 'service.yaml']:
        path = service_dir / name
        if path.exists():
            return path
    return None


def parse_service_manifest(service_dir: Path, chart_name: str):
    service_file = get_first_service_file(service_dir)
    if not service_file:
        return {
            'name': chart_name,
            'type': 'ClusterIP',
            'port': 80,
            'targetPort': 80,
            'labels': {},
            'selectorLabels': {},
        }
    svc = safe_load_yaml(service_file)
    svc_spec = svc.get('spec', {})
    ports = svc_spec.get('ports', [])
    first_port = ports[0] if ports else {}
    return {
        'name': svc.get('metadata', {}).get('name', chart_name),
        'type': svc_spec.get('type', 'ClusterIP'),
        'port': first_port.get('port', 80),
        'targetPort': first_port.get('targetPort', first_port.get('port', 80)),
        'labels': svc.get('metadata', {}).get('labels', {}),
        'selectorLabels': svc_spec.get('selector', {}),
    }


def parse_deploy_manifest(service_dir: Path, chart_name: str):
    deploy_file = service_dir / 'deploy.yaml'
    deploy = safe_load_yaml(deploy_file)
    spec = deploy.get('spec', {})
    template = spec.get('template', {})
    pod = template.get('spec', {})
    containers = pod.get('containers', []) or []
    main_container = containers[0] if containers else {}
    image = main_container.get('image', '')
    repository, tag = (image.split(':', 1) + ['latest'])[:2] if ':' in image else (image, 'latest')
    return {
        'name': deploy.get('metadata', {}).get('name', chart_name),
        'labels': deploy.get('metadata', {}).get('labels', {}) or {},
        'templateLabels': template.get('metadata', {}).get('labels', {}) or {},
        'selectorLabels': spec.get('selector', {}).get('matchLabels', {}) or {},
        'replicaCount': spec.get('replicas', 1),
        'serviceAccountName': pod.get('serviceAccountName', 'default'),
        'image': {
            'repository': repository,
            'tag': tag,
            'pullPolicy': main_container.get('imagePullPolicy', 'IfNotPresent'),
        },
        'resources': main_container.get('resources', {}) or {},
        'env': main_container.get('env', []) or [],
        'volumeMounts': main_container.get('volumeMounts', []) or [],
        'initContainers': pod.get('initContainers', []) or [],
        'volumes': pod.get('volumes', []) or [],
        'readinessProbe': main_container.get('readinessProbe', {}) or {},
        'livenessProbe': main_container.get('livenessProbe', {}) or {},
    }


def parse_ingress_manifest(service_dir: Path):
    ingress_file = service_dir / 'ingress.yaml'
    if not ingress_file.exists():
        return None
    ingress = safe_load_yaml(ingress_file)
    return {
        'enabled': True,
        'name': ingress.get('metadata', {}).get('name'),
        'annotations': ingress.get('metadata', {}).get('annotations', {}),
        'spec': ingress.get('spec', {}),
    }


def parse_configmaps(service_dir: Path):
    configmaps = []
    for filename in sorted(['configmap.yaml', 'cm.yaml']):
        path = service_dir / filename
        if not path.exists():
            continue
        cm = safe_load_yaml(path)
        configmaps.append({
            'name': cm.get('metadata', {}).get('name'),
            'data': cm.get('data', {}),
        })
    return configmaps


def create_service_chart(service_dir: Path):
    chart_name = service_dir.name
    deploy = parse_deploy_manifest(service_dir, chart_name)
    svc = parse_service_manifest(service_dir, chart_name)
    ingress = parse_ingress_manifest(service_dir)
    configmaps = parse_configmaps(service_dir)

    values = {
        'name': deploy['name'],
        'service': {
            'name': svc['name'],
            'type': svc['type'],
            'port': svc['port'],
            'targetPort': svc['targetPort'],
        },
        'selectorLabels': deploy['selectorLabels'] or svc['selectorLabels'] or deploy['templateLabels'],
        'templateLabels': deploy['templateLabels'] or deploy['labels'],
        'replicaCount': deploy['replicaCount'],
        'serviceAccountName': deploy['serviceAccountName'],
        'image': deploy['image'],
        'resources': deploy['resources'],
        'env': deploy['env'],
        'volumeMounts': deploy['volumeMounts'],
        'initContainers': deploy['initContainers'],
        'volumes': deploy['volumes'],
        'readinessProbe': deploy['readinessProbe'],
        'livenessProbe': deploy['livenessProbe'],
        'ingress': ingress or {'enabled': False, 'annotations': {}, 'spec': {}},
        'configMaps': configmaps,
    }

    templates = {
        'deployment.yaml': DEPLOYMENT_TEMPLATE,
        'service.yaml': SERVICE_TEMPLATE,
    }
    if ingress:
        templates['ingress.yaml'] = INGRESS_TEMPLATE
    if configmaps:
        templates['configmap.yaml'] = CONFIGMAP_TEMPLATE

    write_chart(chart_name, deploy['image']['tag'], values, templates)


def create_common_chart():
    common_dir = k8s_root / 'common'
    if not common_dir.exists():
        return

    namespace = safe_load_yaml(common_dir / 'namespace.yaml')
    service_account = safe_load_yaml(common_dir / 'serviceaccount.yaml')
    pdb_docs = safe_load_all_yaml(common_dir / 'pdb.yaml')
    hpa_docs = safe_load_all_yaml(common_dir / 'hpa.yaml')
    network_policy = safe_load_yaml(common_dir / 'networkpolicy.yaml')

    values = {
        'namespace': {
            'name': namespace.get('metadata', {}).get('name', 'ecommerce'),
            'labels': namespace.get('metadata', {}).get('labels', {}),
        },
        'serviceAccount': {
            'name': service_account.get('metadata', {}).get('name', 'opentelemetry-demo'),
            'labels': service_account.get('metadata', {}).get('labels', {}),
        },
        'pdbs': [
            {
                'name': pdb.get('metadata', {}).get('name'),
                'labels': pdb.get('metadata', {}).get('labels', {}),
                'minAvailable': pdb.get('spec', {}).get('minAvailable', 1),
                'selector': pdb.get('spec', {}).get('selector', {}),
            }
            for pdb in pdb_docs
        ],
        'hpas': [
            {
                'name': hpa.get('metadata', {}).get('name'),
                'labels': hpa.get('metadata', {}).get('labels', {}),
                'scaleTargetRef': hpa.get('spec', {}).get('scaleTargetRef', {}),
                'minReplicas': hpa.get('spec', {}).get('minReplicas', 1),
                'maxReplicas': hpa.get('spec', {}).get('maxReplicas', 4),
                'targetCPUUtilizationPercentage': hpa.get('spec', {}).get('metrics', [{}])[0].get('resource', {}).get('target', {}).get('averageUtilization', 90),
            }
            for hpa in hpa_docs
        ],
        'networkPolicy': {
            'name': network_policy.get('metadata', {}).get('name', 'ecommerce-network-policy'),
            'labels': network_policy.get('metadata', {}).get('labels', {}),
            'podSelector': network_policy.get('spec', {}).get('podSelector', {}),
            'namespaceSelector': network_policy.get('spec', {}).get('ingress', [])[0].get('from', [])[0].get('namespaceSelector', {}),
        },
    }

    write_chart('common', '1.0.0', values, {
        'namespace.yaml': COMMON_NAMESPACE_TEMPLATE,
        'serviceaccount.yaml': COMMON_SERVICEACCOUNT_TEMPLATE,
        'pdb.yaml': COMMON_PDB_TEMPLATE,
        'hpa.yaml': COMMON_HPA_TEMPLATE,
        'networkpolicy.yaml': COMMON_NETWORKPOLICY_TEMPLATE,
    })


if helm_root.exists():
    shutil.rmtree(helm_root)
helm_root.mkdir(parents=True, exist_ok=True)

for service_dir in sorted(k8s_root.iterdir()):
    if not service_dir.is_dir():
        continue
    if service_dir.name == 'common':
        continue
    create_service_chart(service_dir)

create_common_chart()

print('Generated parameterized Helm charts for every service and common resources under helm/')
