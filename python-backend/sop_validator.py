#!/usr/bin/env python3
"""
SOP文档自动验证工具
用法: python sop_validator.py path/to/sop.md
"""

import re
import sys
from pathlib import Path
from typing import Dict, List, Tuple
from datetime import datetime

class SOPValidator:
    def __init__(self, sop_file: str):
        self.sop_file = Path(sop_file)
        if not self.sop_file.exists():
            raise FileNotFoundError(f"SOP文件不存在: {sop_file}")
        
        self.content = self.sop_file.read_text(encoding='utf-8')
        self.issues = []
        self.warnings = []
        self.info = []
        self.sop_type = self._detect_sop_type()  # 'code', 'process', or 'mixed'
    
    def _detect_sop_type(self) -> str:
        """自动检测SOP类型"""
        code_blocks = re.findall(r'```\w*\n.*?```', self.content, re.DOTALL)
        code_chars = sum(len(block) for block in code_blocks)
        total_chars = len(self.content)
        
        if code_chars == 0:
            return 'process'  # 纯流程文档
        elif code_chars / total_chars > 0.3:
            return 'code'  # 代码为主
        else:
            return 'mixed'  # 混合类型
    
    def validate(self) -> Tuple[bool, List[str], List[str]]:
        """执行所有验证检查"""
        print(f"🔍 正在验证: {self.sop_file.name}")
        print(f"📋 SOP类型: {self.sop_type.upper()}")
        print("=" * 60)
        
        self.check_structure()
        self.check_completeness()
        
        # 只对包含代码的SOP检查代码块
        if self.sop_type in ['code', 'mixed']:
            self.check_code_blocks()
        else:
            self.info.append("ℹ️ 纯流程SOP，跳过代码检查")
        
        self.check_examples()
        self.check_maintainability()
        self.check_readability()
        
        is_valid = len(self.issues) == 0
        return is_valid, self.issues, self.warnings
    
    def check_structure(self):
        """检查文档结构"""
        # 检查是否有主标题
        main_title = re.search(r'^#\s+(.+)', self.content, re.MULTILINE)
        if not main_title:
            self.issues.append("❌ 缺少主标题（# 标题）")
        else:
            self.info.append(f"📄 主标题: {main_title.group(1)}")
        
        # 检查章节标题
        headings = re.findall(r'^(#{1,6})\s+(.+)', self.content, re.MULTILINE)
        if len(headings) < 3:
            self.warnings.append("⚠️ 章节数量较少，建议增加结构化内容")
        
        self.info.append(f"📑 章节数量: {len(headings)}")
        
        # 检查层级跳跃
        prev_level = 0
        for heading, title in headings:
            level = len(heading)
            if level - prev_level > 1:
                self.warnings.append(f"⚠️ 章节层级跳跃: {title} (从 {'#'*prev_level} 跳到 {'#'*level})")
            prev_level = level
        
        # 检查是否有目录
        if "目录" in self.content or "Table of Contents" in self.content:
            self.info.append("✅ 包含目录")
        elif len(headings) > 10:
            self.warnings.append("⚠️ 章节较多但缺少目录，建议添加")
    
    def check_completeness(self):
        """检查完整性"""
        required_sections = [
            ("概述", r'##\s*(概述|Overview|简介|Introduction)'),
            ("输入", r'##\s*(输入|Input|参数|Parameters)'),
            ("输出", r'##\s*(输出|Output|结果|Results)'),
            ("步骤", r'##\s*(步骤|流程|Steps|Process|Procedure)'),
        ]
        
        missing = []
        for name, pattern in required_sections:
            if not re.search(pattern, self.content, re.IGNORECASE):
                missing.append(name)
        
        if missing:
            self.issues.append(f"❌ 缺少必需章节: {', '.join(missing)}")
        else:
            self.info.append("✅ 所有必需章节完整")
        
        # 检查示例章节
        if not re.search(r'##\s*(示例|Example)', self.content, re.IGNORECASE):
            self.warnings.append("⚠️ 建议添加示例章节")
    
    def check_code_blocks(self):
        """检查代码块"""
        code_blocks = re.findall(r'```(\w+)?\n(.*?)```', self.content, re.DOTALL)
        
        if not code_blocks:
            self.warnings.append("⚠️ 没有代码示例，建议添加")
            return
        
        self.info.append(f"💻 代码块数量: {len(code_blocks)}")
        
        unlabeled = 0
        long_blocks = 0
        
        for lang, code in code_blocks:
            if not lang:
                unlabeled += 1
            
            # 检查代码长度
            lines = code.strip().split('\n')
            if len(lines) > 50:
                long_blocks += 1
        
        if unlabeled > 0:
            self.warnings.append(f"⚠️ {unlabeled}个代码块缺少语言标注")
        
        if long_blocks > 0:
            self.warnings.append(f"⚠️ {long_blocks}个代码块过长（>50行），建议拆分")
    
    def check_examples(self):
        """检查示例"""
        example_count = len(re.findall(r'##\s*(示例|Example)', self.content, re.IGNORECASE))
        
        if example_count == 0:
            self.warnings.append("⚠️ 缺少示例章节")
        elif example_count == 1:
            self.warnings.append("⚠️ 只有1个示例，建议提供至少2个（标准情况+边界情况）")
        else:
            self.info.append(f"✅ 示例数量: {example_count}")
    
    def check_maintainability(self):
        """检查可维护性"""
        # 检查版本号
        version_match = re.search(r'(Version|版本):\s*(\d+\.\d+)', self.content, re.IGNORECASE)
        if not version_match:
            self.warnings.append("⚠️ 缺少版本号")
        else:
            self.info.append(f"📌 版本: {version_match.group(2)}")
        
        # 检查日期
        date_match = re.search(r'(\d{4}-\d{2}-\d{2})', self.content)
        if not date_match:
            self.warnings.append("⚠️ 缺少创建/更新日期")
        else:
            self.info.append(f"📅 日期: {date_match.group(1)}")
        
        # 检查更新日志
        if re.search(r'(更新日志|Changelog|History)', self.content, re.IGNORECASE):
            self.info.append("✅ 包含更新日志")
        else:
            self.warnings.append("⚠️ 建议添加更新日志章节")
        
        # 检查章节长度
        sections = re.split(r'\n##\s+', self.content)
        long_sections = []
        for i, section in enumerate(sections[1:], 1):
            lines = section.count('\n')
            if lines > 100:
                section_title = section.split('\n')[0]
                long_sections.append(f"{section_title} ({lines}行)")
        
        if long_sections:
            self.warnings.append(f"⚠️ 以下章节过长，建议拆分: {', '.join(long_sections)}")
    
    def check_readability(self):
        """检查可读性"""
        # 统计文档长度
        lines = self.content.count('\n')
        words = len(self.content.split())
        
        self.info.append(f"📏 文档长度: {lines}行, {words}词")
        
        # 检查列表使用
        bullet_lists = len(re.findall(r'^\s*[-*]\s+', self.content, re.MULTILINE))
        numbered_lists = len(re.findall(r'^\s*\d+\.\s+', self.content, re.MULTILINE))
        
        if bullet_lists + numbered_lists < 5:
            self.warnings.append("⚠️ 列表使用较少，建议使用列表提高可读性")
        
        # 检查表格使用
        tables = len(re.findall(r'\|.*\|', self.content))
        if tables > 0:
            self.info.append(f"📊 包含表格: {tables // 3}个")  # 粗略估计
        
        # 检查代码与文字比例（仅对包含代码的SOP）
        if self.sop_type in ['code', 'mixed']:
            code_chars = sum(len(code) for code in re.findall(r'```\w*\n(.*?)```', self.content, re.DOTALL))
            text_chars = len(self.content) - code_chars
            
            if text_chars > 0:
                ratio = code_chars / text_chars
                if ratio < 0.1:
                    self.warnings.append("⚠️ 代码示例较少，建议增加实际代码")
                elif ratio > 0.8:
                    self.warnings.append("⚠️ 代码过多，建议增加说明文字")
    
    def generate_report(self) -> str:
        """生成验证报告"""
        report = []
        report.append("=" * 60)
        report.append(f"📋 SOP验证报告")
        report.append("=" * 60)
        report.append(f"文件: {self.sop_file.name}")
        report.append(f"路径: {self.sop_file.absolute()}")
        report.append(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        report.append("=" * 60)
        report.append("")
        
        # 基本信息
        if self.info:
            report.append("📊 基本信息:")
            for info in self.info:
                report.append(f"  {info}")
            report.append("")
        
        # 错误
        if self.issues:
            report.append(f"❌ 错误 ({len(self.issues)}):")
            for issue in self.issues:
                report.append(f"  {issue}")
            report.append("")
        
        # 警告
        if self.warnings:
            report.append(f"⚠️  警告 ({len(self.warnings)}):")
            for warning in self.warnings:
                report.append(f"  {warning}")
            report.append("")
        
        # 总结
        report.append("=" * 60)
        if not self.issues and not self.warnings:
            report.append("✅ 验证通过 - 没有发现问题")
        elif not self.issues:
            report.append(f"✅ 验证通过 - 有 {len(self.warnings)} 个改进建议")
        else:
            report.append(f"❌ 验证失败 - 发现 {len(self.issues)} 个错误")
        report.append("=" * 60)
        
        return '\n'.join(report)
    
    def save_report(self, output_file: str = None):
        """保存报告到文件"""
        if output_file is None:
            output_file = self.sop_file.with_suffix('.validation_report.txt')
        
        report = self.generate_report()
        Path(output_file).write_text(report, encoding='utf-8')
        print(f"\n💾 报告已保存: {output_file}")

def main():
    if len(sys.argv) < 2:
        print("用法: python sop_validator.py <sop_file.md> [--save-report]")
        print("\n示例:")
        print("  python sop_validator.py Chatskills.md")
        print("  python sop_validator.py Chatskills.md --save-report")
        sys.exit(1)
    
    sop_file = sys.argv[1]
    save_report = '--save-report' in sys.argv
    
    try:
        validator = SOPValidator(sop_file)
        is_valid, issues, warnings = validator.validate()
        
        print("\n" + validator.generate_report())
        
        if save_report:
            validator.save_report()
        
        # 返回退出码
        if not is_valid:
            sys.exit(1)
        else:
            sys.exit(0)
    
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