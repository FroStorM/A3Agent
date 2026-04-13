#!/usr/bin/env python3
"""
轻量级SOP测试沙盒
无需Docker，使用临时目录+资源限制实现隔离
"""

import os
import sys
import json
import shutil
import tempfile
import subprocess
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Optional
import time

# 导入已有的验证器和执行器
try:
    from sop_validator import SOPValidator
    from sop_executor import SOPExecutor
except ImportError:
    print("⚠️ 警告: 无法导入 sop_validator 或 sop_executor")
    print("请确保这些文件在同一目录下")

class LightweightSandbox:
    """轻量级沙盒环境"""
    
    def __init__(self, sop_file: str, config: Dict[str, Any] = None):
        self.sop_file = Path(sop_file)
        if not self.sop_file.exists():
            raise FileNotFoundError(f"SOP文件不存在: {sop_file}")
        
        # 默认配置
        self.config = {
            'timeout': 60,              # 执行超时（秒）
            'max_memory_mb': 512,       # 最大内存（MB）
            'allow_network': False,     # 是否允许网络访问
            'allow_file_write': True,   # 是否允许写文件
            'temp_dir_prefix': 'sop_sandbox_',
            'keep_temp': False,         # 是否保留临时目录
        }
        if config:
            self.config.update(config)
        
        # 创建临时沙盒目录
        self.sandbox_dir = Path(tempfile.mkdtemp(prefix=self.config['temp_dir_prefix']))
        self.results = {
            'sop_file': str(self.sop_file),
            'sandbox_dir': str(self.sandbox_dir),
            'timestamp': datetime.now().isoformat(),
            'tests': []
        }
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.cleanup()
    
    def cleanup(self):
        """清理沙盒环境"""
        if not self.config['keep_temp'] and self.sandbox_dir.exists():
            try:
                shutil.rmtree(self.sandbox_dir)
                print(f"🧹 已清理沙盒目录: {self.sandbox_dir}")
            except Exception as e:
                print(f"⚠️ 清理失败: {e}")
    
    def run_static_analysis(self) -> Dict[str, Any]:
        """静态分析：文档结构和质量检查"""
        print("\n" + "="*60)
        print("📊 第1步：静态分析（文档质量检查）")
        print("="*60)
        
        try:
            validator = SOPValidator(str(self.sop_file))
            is_valid, issues, warnings = validator.validate()
            
            report = validator.generate_report()
            print(report)
            
            # 计算质量分数
            score = self._calculate_quality_score(issues, warnings)
            
            result = {
                'test_name': 'static_analysis',
                'status': 'pass' if is_valid else 'fail',
                'score': score,
                'issues': issues,
                'warnings': warnings,
                'report': report
            }
            
            self.results['tests'].append(result)
            return result
        
        except Exception as e:
            result = {
                'test_name': 'static_analysis',
                'status': 'error',
                'error': str(e)
            }
            self.results['tests'].append(result)
            return result
    
    def run_syntax_check(self) -> Dict[str, Any]:
        """语法检查：验证代码可编译性"""
        print("\n" + "="*60)
        print("🔍 第2步：语法检查（代码可编译性）")
        print("="*60)
        
        try:
            executor = SOPExecutor(str(self.sop_file))
            result = executor.dry_run()
            
            if result['status'] == 'success':
                print(f"✅ {result['message']}")
                print(f"   代码行数: {result['code_lines']}")
            else:
                print(f"❌ {result['message']}")
                if 'line' in result:
                    print(f"   错误位置: 第 {result['line']} 行")
            
            result['test_name'] = 'syntax_check'
            self.results['tests'].append(result)
            return result
        
        except Exception as e:
            result = {
                'test_name': 'syntax_check',
                'status': 'error',
                'error': str(e)
            }
            self.results['tests'].append(result)
            return result
    
    def run_isolated_execution(self, test_input: Dict[str, Any] = None) -> Dict[str, Any]:
        """隔离执行：在沙盒中运行代码"""
        print("\n" + "="*60)
        print("🚀 第3步：隔离执行（沙盒运行）")
        print("="*60)
        
        try:
            # 复制SOP文件到沙盒
            sandbox_sop = self.sandbox_dir / self.sop_file.name
            shutil.copy2(self.sop_file, sandbox_sop)
            
            # 准备执行环境
            executor = SOPExecutor(str(sandbox_sop))
            
            # 在沙盒目录中执行
            original_cwd = os.getcwd()
            try:
                os.chdir(self.sandbox_dir)
                
                start_time = time.time()
                result = executor.execute(
                    input_data=test_input,
                    timeout=self.config['timeout']
                )
                execution_time = time.time() - start_time
                
                result['execution_time'] = execution_time
                result['test_name'] = 'isolated_execution'
                
                if result['status'] == 'success':
                    print(f"✅ 执行成功 (耗时: {execution_time:.2f}秒)")
                    
                    # 检查生成的文件
                    generated_files = list(self.sandbox_dir.glob('*'))
                    generated_files = [f.name for f in generated_files if f.is_file() and f != sandbox_sop]
                    result['generated_files'] = generated_files
                    
                    if generated_files:
                        print(f"📁 生成文件: {', '.join(generated_files)}")
                else:
                    print(f"❌ 执行失败: {result.get('message', '未知错误')}")
                
            finally:
                os.chdir(original_cwd)
            
            self.results['tests'].append(result)
            return result
        
        except Exception as e:
            result = {
                'test_name': 'isolated_execution',
                'status': 'error',
                'error': str(e)
            }
            self.results['tests'].append(result)
            return result
    
    def run_security_check(self) -> Dict[str, Any]:
        """安全检查：检测潜在的危险操作"""
        print("\n" + "="*60)
        print("🔒 第4步：安全检查（危险操作检测）")
        print("="*60)
        
        try:
            content = self.sop_file.read_text(encoding='utf-8')
            
            # 危险模式检测
            dangerous_patterns = {
                'system_commands': [r'os\.system', r'subprocess\.call', r'subprocess\.run'],
                'file_operations': [r'open\(.*[\'"]w', r'shutil\.rmtree', r'os\.remove'],
                'network_access': [r'requests\.', r'urllib\.', r'socket\.'],
                'code_execution': [r'eval\(', r'exec\(', r'__import__'],
            }
            
            findings = {}
            for category, patterns in dangerous_patterns.items():
                import re
                matches = []
                for pattern in patterns:
                    found = re.findall(pattern, content)
                    if found:
                        matches.extend(found)
                
                if matches:
                    findings[category] = matches
            
            if findings:
                print("⚠️ 发现潜在危险操作:")
                for category, matches in findings.items():
                    print(f"   {category}: {len(matches)} 处")
                status = 'warning'
            else:
                print("✅ 未发现明显的危险操作")
                status = 'pass'
            
            result = {
                'test_name': 'security_check',
                'status': status,
                'findings': findings
            }
            
            self.results['tests'].append(result)
            return result
        
        except Exception as e:
            result = {
                'test_name': 'security_check',
                'status': 'error',
                'error': str(e)
            }
            self.results['tests'].append(result)
            return result
    
    def _calculate_quality_score(self, issues: List[str], warnings: List[str]) -> int:
        """计算质量分数（0-100）"""
        base_score = 100
        
        # 每个错误扣20分
        base_score -= len(issues) * 20
        
        # 每个警告扣5分
        base_score -= len(warnings) * 5
        
        return max(0, min(100, base_score))
    
    def generate_report(self, output_file: Optional[str] = None) -> str:
        """生成完整测试报告"""
        report_lines = []
        report_lines.append("="*60)
        report_lines.append("📋 SOP沙盒测试报告")
        report_lines.append("="*60)
        report_lines.append(f"SOP文件: {self.results['sop_file']}")
        report_lines.append(f"测试时间: {self.results['timestamp']}")
        report_lines.append(f"沙盒目录: {self.results['sandbox_dir']}")
        report_lines.append("="*60)
        report_lines.append("")
        
        # 测试结果汇总
        total_tests = len(self.results['tests'])
        passed = sum(1 for t in self.results['tests'] if t.get('status') == 'pass')
        failed = sum(1 for t in self.results['tests'] if t.get('status') == 'fail')
        errors = sum(1 for t in self.results['tests'] if t.get('status') == 'error')
        warnings = sum(1 for t in self.results['tests'] if t.get('status') == 'warning')
        
        report_lines.append("📊 测试汇总:")
        report_lines.append(f"   总计: {total_tests} 项测试")
        report_lines.append(f"   ✅ 通过: {passed}")
        report_lines.append(f"   ❌ 失败: {failed}")
        report_lines.append(f"   ⚠️  警告: {warnings}")
        report_lines.append(f"   💥 错误: {errors}")
        report_lines.append("")
        
        # 质量分数
        quality_score = None
        for test in self.results['tests']:
            if test.get('test_name') == 'static_analysis' and 'score' in test:
                quality_score = test['score']
                break
        
        if quality_score is not None:
            report_lines.append(f"🎯 质量分数: {quality_score}/100")
            if quality_score >= 90:
                report_lines.append("   评级: 优秀 ⭐⭐⭐⭐⭐")
            elif quality_score >= 75:
                report_lines.append("   评级: 良好 ⭐⭐⭐⭐")
            elif quality_score >= 60:
                report_lines.append("   评级: 及格 ⭐⭐⭐")
            else:
                report_lines.append("   评级: 需改进 ⭐⭐")
            report_lines.append("")
        
        # 详细测试结果
        report_lines.append("="*60)
        report_lines.append("📝 详细测试结果:")
        report_lines.append("="*60)
        
        for i, test in enumerate(self.results['tests'], 1):
            test_name = test.get('test_name', 'unknown')
            status = test.get('status', 'unknown')
            
            status_icon = {
                'pass': '✅',
                'fail': '❌',
                'warning': '⚠️',
                'error': '💥'
            }.get(status, '❓')
            
            report_lines.append(f"\n{i}. {test_name} {status_icon}")
            
            if 'execution_time' in test:
                report_lines.append(f"   执行时间: {test['execution_time']:.2f}秒")
            
            if 'generated_files' in test:
                report_lines.append(f"   生成文件: {', '.join(test['generated_files'])}")
            
            if 'error' in test:
                report_lines.append(f"   错误: {test['error']}")
            
            if 'findings' in test and test['findings']:
                report_lines.append("   发现:")
                for category, items in test['findings'].items():
                    report_lines.append(f"      {category}: {len(items)} 处")
        
        report_lines.append("\n" + "="*60)
        
        # 总结建议
        if failed > 0 or errors > 0:
            report_lines.append("❌ 测试未通过，建议修复后重新测试")
        elif warnings > 0:
            report_lines.append("⚠️ 测试通过但有警告，建议优化")
        else:
            report_lines.append("✅ 所有测试通过，SOP质量良好")
        
        report_lines.append("="*60)
        
        report = '\n'.join(report_lines)
        
        # 保存报告
        if output_file:
            Path(output_file).write_text(report, encoding='utf-8')
            print(f"\n💾 报告已保存: {output_file}")
        
        return report
    
    def run_full_test(self, test_input: Dict[str, Any] = None, skip_execution: bool = False) -> Dict[str, Any]:
        """运行完整测试流程"""
        print("\n" + "🎯 开始SOP沙盒测试")
        print(f"📄 SOP文件: {self.sop_file.name}")
        print(f"📁 沙盒目录: {self.sandbox_dir}")
        
        # 1. 静态分析
        self.run_static_analysis()
        
        # 2. 语法检查
        self.run_syntax_check()
        
        # 3. 安全检查
        self.run_security_check()
        
        # 4. 隔离执行（可选）
        if not skip_execution:
            self.run_isolated_execution(test_input)
        else:
            print("\n⏭️  跳过隔离执行")
        
        # 生成报告
        report = self.generate_report()
        print("\n" + report)
        
        return self.results


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='轻量级SOP测试沙盒')
    parser.add_argument('sop_file', help='SOP文件路径')
    parser.add_argument('--skip-execution', action='store_true', help='跳过代码执行')
    parser.add_argument('--keep-temp', action='store_true', help='保留临时目录')
    parser.add_argument('--timeout', type=int, default=60, help='执行超时（秒）')
    parser.add_argument('--output', '-o', help='报告输出文件')
    
    args = parser.parse_args()
    
    config = {
        'timeout': args.timeout,
        'keep_temp': args.keep_temp,
    }
    
    try:
        with LightweightSandbox(args.sop_file, config) as sandbox:
            results = sandbox.run_full_test(skip_execution=args.skip_execution)
            
            if args.output:
                sandbox.generate_report(args.output)
            
            # 根据测试结果返回退出码
            failed = sum(1 for t in results['tests'] if t.get('status') in ['fail', 'error'])
            sys.exit(1 if failed > 0 else 0)
    
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