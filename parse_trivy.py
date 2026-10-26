import json
import sys

def analyze(json_path):
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
        
    counts = {
        'os': {'CRITICAL': 0, 'HIGH': 0, 'MEDIUM': 0, 'LOW': 0, 'TOTAL': 0},
        'python': {'CRITICAL': 0, 'HIGH': 0, 'MEDIUM': 0, 'LOW': 0, 'TOTAL': 0},
        'total': {'CRITICAL': 0, 'HIGH': 0, 'MEDIUM': 0, 'LOW': 0, 'TOTAL': 0}
    }
    
    crit_high_findings = []
    
    for result in data.get('Results', []):
        target = result.get('Target', '')
        r_class = result.get('Class', '') # 'os-pkgs' or 'lang-pkgs'
        r_type = result.get('Type', '')
        
        is_os = (r_class == 'os-pkgs' or r_type in ['debian', 'ubuntu', 'alpine', 'redhat'])
        category = 'os' if is_os else 'python'
        
        for vuln in result.get('Vulnerabilities', []) or []:
            sev = vuln.get('Severity', '').upper()
            if sev in counts[category]:
                counts[category][sev] += 1
                counts[category]['TOTAL'] += 1
                counts['total'][sev] += 1
                counts['total']['TOTAL'] += 1
                
            if sev in ['CRITICAL', 'HIGH']:
                crit_high_findings.append({
                    'category': category,
                    'package': vuln.get('PkgName'),
                    'installed': vuln.get('InstalledVersion'),
                    'fixed': vuln.get('FixedVersion', 'None'),
                    'id': vuln.get('VulnerabilityID'),
                    'severity': sev,
                    'title': vuln.get('Title', '')
                })
                
    return counts, crit_high_findings

if __name__ == '__main__':
    if len(sys.argv) > 1:
        path = sys.argv[1]
        counts, crit_high = analyze(path)
        print(json.dumps({'counts': counts, 'findings': crit_high}, indent=2))
