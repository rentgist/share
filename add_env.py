with open(r'C:\Users\로컬\Desktop\my-quant-bot\final.py', 'r', encoding='utf-8') as f:
    content = f.read()

if 'from dotenv import load_dotenv' not in content:
    content = 'from dotenv import load_dotenv\nload_dotenv()\n' + content
    with open(r'C:\Users\로컬\Desktop\my-quant-bot\final.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print('Added load_dotenv')
