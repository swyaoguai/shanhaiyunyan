import json
with open('C:/Users/wen/Desktop/AGENT/_temp_tree.json') as f:
    data = json.load(f)
count = 0
for item in data.get('tree',[]):
    p = item['path']
    if p.startswith('examples/') and not p.endswith('/'):
        print(p)
        count += 1
        if count > 60:
            break