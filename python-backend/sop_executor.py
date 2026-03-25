#!/usr/bin/env python3
"""
SOP自动执行器
根据SOP文档自动生成和执行测试
"""

import json
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, Any, List
import re

class SOPExecutor:
    def __init__(self, sop_file: str):
        self.sop_file = Path(sop_file)
        if not self.sop_file.exists():
            raise FileNotFoundError(f"SOP文件不存在: {sop_file}")
        
        self.sop_content = self.sop_file.read_text(encoding='utf-8')
        self.code_blocks = self._extract_code_blocks()
    
    def _extract_code_blocks(self) -> List[Dict[str, str]]:
        """从SOP中提取所有代码块"""
        pattern = r'```(\w+)?\n(.*?)```'
        matches = re.findall(pattern, self.sop_content, re.DOTALL)
        
        blocks = []
        for lang, code in matches:
            blocks.append({
                'language': lang or 'unknown',
                'code': code.strip()
            })
        
        return blocks
    
    def get_python_code(self) -> str:
        """获取第一个Python代码块"""
        for block in self.code_blocks:
            if block['language'].lower() == 'python':
                return block['code']
        return ""
    
    def execute(self, input_data: Dict[str, Any] = None, timeout: int = 60) -> Dict[str, Any]:
        """执行SOP定义的流程"""
        try:
            # 1. 获取Python代码
            code = self.get_python_code()
            if not code:
                return {
                    "status": "error",
                    "message": "SOP中没有找到Python代码块"
                }
            
            # 2. 准备输入数据
            if input_data:
                input_file = Path(tempfile.mktemp(suffix='.json'))
                input_file.write_text(json.dumps(input_data, ensure_ascii=False, indent=2))
                
                # 在代码中注入输入文件路径
                code = f"INPUT_FILE = '{input_file}'\n" + code
            
            # 3. 创建临时脚本
            script_file = Path(tempfile.mktemp(suffix='.py'))
            script_file.write_text(code, encoding='utf-8')
            
            print(f"🚀 执行SOP: {self.sop_file.name}")
            print(f"📝 临时脚本: {script_file}")
            
            # 4. 执行脚本
            result = subprocess.run(
                ["python3", str(script_file)],
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=script_file.parent
            )
            
            # 5. 清理临时文件
            script_file.unlink(missing_ok=True)
            if input_data:
                input_file.unlink(missing_ok=True)
            
            # 6. 返回结果
            if result.returncode == 0:
                return {
                    "status": "success",
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                    "returncode": 0
                }
            else:
                return {
                    "status": "error",
                    "returncode": result.returncode,
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                    "message": f"脚本执行失败，退出码: {result.returncode}"
                }
        
        except subprocess.TimeoutExpired:
            return {
                "status": "error",
                "message": f"执行超时（>{timeout}秒）"
            }
        except Exception as e:
            return {
                "status": "error",
                "message": f"执行异常: {str(e)}"
            }
    
    def dry_run(self) -> Dict[str, Any]:
        """干运行：检查代码但不执行"""
        code = self.get_python_code()
        if not code:
            return {
                "status": "error",
                "message": "没有找到Python代码"
            }
        
        # 语法检查
        try:
            compile(code, '<string>', 'exec')
            return {
                "status": "success",
                "message": "代码语法正确",
                "code_lines": len(code.split('\n')),
                "code_preview": code[:200] + "..." if len(code) > 200 else code
            }
        except SyntaxError as e:
            return {
                "status": "error",
                "message": f"语法错误: {e.msg}",
                "line": e.lineno,
                "offset": e.offset
            }
    
    def list_code_blocks(self) -> List[Dict[str, Any]]:
        """列出所有代码块"""
        result = []
        for i, block in enumerate(self.code_blocks, 1):
            result.append({
                "index": i,
                "language": block['language'],
                "lines": len(block['code'].split('\n')),
                "preview": block['code'][:100] + "..." if len(block['code']) > 100 else block['code']
            })
        return result

def main():
    import sys
    
    if len(sys.argv) < 2:
        print("用法: python sop_executor.py <sop_file.md> [--dry-run|--list|--execute]")
        print("\n选项:")
        print("  --dry-run    检查代码语法但不执行")
        print("  --list       列出所有代码块")
        print("  --execute    执行代码（默认）")
        print("\n示例:")
        print("  python sop_executor.py Chatskills.md --dry-run")
        print("  python sop_executor.py Chatskills.md --execute")
        sys.exit(1)
    
    sop_file = sys.argv[1]
    mode = sys.argv[2] if len(sys.argv) > 2 else '--execute'
    
    try:
        executor = SOPExecutor(sop_file)
        
        if mode == '--dry-run':
            result = executor.dry_run()
            print(json.dumps(result, indent=2, ensure_ascii=False))
        
        elif mode == '--list':
            blocks = executor.list_code_blocks()
            print(f"找到 {len(blocks)} 个代码块:\n")
            for block in blocks:
                print(f"[{block['index']}] {block['language']} ({block['lines']}行)")
                print(f"    {block['preview']}\n")
        
        elif mode == '--execute':
            result = executor.execute()
            print("\n" + "="*60)
            print("执行结果:")
            print("="*60)
            print(f"状态: {result['status']}")
            if result['status'] == 'success':
                print(f"\n标准输出:\n{result['stdout']}")
                if result['stderr']:
                    print(f"\n标准错误:\n{result['stderr']}")
            else:
                print(f"错误: {result.get('message', '未知错误')}")
                if 'stdout' in result:
                    print(f"\n标准输出:\n{result['stdout']}")
                if 'stderr' in result:
                    print(f"\n标准错误:\n{result['stderr']}")
            print("="*60)
            
            sys.exit(0 if result['status'] == 'success' else 1)
        
        else:
            print(f"未知选项: {mode}")
            sys.exit(1)
    
    except FileNotFoundError as e:
        print(f"❌ 错误: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"❌ 未预期的错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()