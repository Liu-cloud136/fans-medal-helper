#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
安全检查脚本 - 检查配置文件中的敏感信息
用于在提交代码前检查是否有隐私信息泄露
"""

import os
import re
import yaml
import sys
from pathlib import Path


def check_file_sensitive(filepath):
    """检查文件是否包含敏感信息"""
    sensitive_patterns = [
        r'access_key\s*:\s*["\']?[a-zA-Z0-9]{20,}["\']?',  # access_key
        r'secret\s*:\s*["\']?[a-zA-Z0-9]{20,}["\']?',       # 各种secret
        r'token\s*:\s*["\']?[a-zA-Z0-9]{20,}["\']?',        # 各种token
        r'password\s*:\s*["\']?.+["\']?',                    # 密码
        r'api_key\s*:\s*["\']?[a-zA-Z0-9]{20,}["\']?',     # API密钥
        r'sk_[a-zA-Z0-9]{20,}',                              # Stripe等sk_开头的密钥
        r'[a-zA-Z0-9]{32,}',                                # 32位以上的长字符串
        r'APPKEY\s*=\s*["\']?[a-zA-Z0-9]{16,}["\']?',     # 硬编码的APPKEY
        r'APPSECRET\s*=\s*["\']?[a-zA-Z0-9]{32,}["\']?',   # 硬编码的APPSECRET
        r'os\.environ\.get\(".*?",\s*["\']?[a-zA-Z0-9]{20,}["\']?\)',  # 带默认值的环境变量
    ]
    
    issues = []
    
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
            
        for pattern in sensitive_patterns:
            matches = re.finditer(pattern, content, re.IGNORECASE)
            for match in matches:
                line_num = content[:match.start()].count('\n') + 1
                line_content = content.split('\n')[line_num - 1].strip()
                
                # 排除示例和注释
                if ('example' in filepath.lower() or 
                    '示例' in line_content or 
                    'example' in line_content.lower() or
                    'xxxx' in line_content or
                    'xxx' in line_content or
                    line_content.strip().startswith('#')):
                    continue
                    
                issues.append({
                    'file': filepath,
                    'line': line_num,
                    'content': line_content,
                    'pattern': pattern
                })
                
    except Exception as e:
        issues.append({
            'file': filepath,
            'error': str(e)
        })
    
    return issues


def check_yaml_config(filepath):
    """检查YAML配置文件的敏感信息"""
    issues = []
    
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
            
        # 检查access_key
        if isinstance(config, dict) and 'USERS' in config:
            users = config['USERS']
            if isinstance(users, list):
                for i, user in enumerate(users):
                    if isinstance(user, dict) and 'access_key' in user:
                        access_key = user['access_key']
                        if access_key and len(str(access_key)) > 10:
                            # 排除示例值
                            if not any(x in str(access_key).lower() for x in ['xxx', 'example', '示例', '你的']):
                                issues.append({
                                    'file': filepath,
                                    'line': f'USERS[{i}].access_key',
                                    'content': f'发现真实的access_key: {str(access_key)[:10]}...'
                                })
                                
        # 检查推送配置
        if isinstance(config, dict):
            if 'SENDKEY' in config and config['SENDKEY']:
                sendkey = config['SENDKEY']
                if len(str(sendkey)) > 10 and 'sct' in str(sendkey):
                    issues.append({
                        'file': filepath,
                        'line': 'SENDKEY',
                        'content': f'发现真实的Server酱密钥: {str(sendkey)[:10]}...'
                    })
                    
            if 'MOREPUSH' in config and config['MOREPUSH']:
                morepush = config['MOREPUSH']
                if isinstance(morepush, dict) and 'params' in morepush:
                    params = morepush['params']
                    for key, value in params.items():
                        if 'token' in key.lower() and value and len(str(value)) > 10:
                            issues.append({
                                'file': filepath,
                                'line': f'MOREPUSH.params.{key}',
                                'content': f'发现推送token: {str(value)[:10]}...'
                            })
                    
    except Exception as e:
        issues.append({
            'file': filepath,
            'error': f'YAML解析错误: {str(e)}'
        })
    
    return issues


def main():
    """主函数"""
    print("🔍 开始检查项目中的敏感信息...")
    
    # 需要检查的文件
    files_to_check = [
        'users.yaml',
        'config.yaml',
        '.env',
        'secrets.txt'
    ]
    
    # 检查所有Python和YAML文件
    for pattern in ['*.py', '*.yaml', '*.yml']:
        for file in Path('.').glob(pattern):
            if 'example' not in file.name.lower():
                files_to_check.append(str(file))
    
    all_issues = []
    
    for filepath in files_to_check:
        if os.path.exists(filepath):
            print(f"\n📁 检查文件: {filepath}")
            
            # 通用敏感信息检查
            issues = check_file_sensitive(filepath)
            
            # YAML特殊检查
            if filepath.endswith(('.yaml', '.yml')):
                yaml_issues = check_yaml_config(filepath)
                issues.extend(yaml_issues)
            
            all_issues.extend(issues)
            
            if issues:
                print("⚠️  发现问题:")
                for issue in issues:
                    if 'error' in issue:
                        print(f"   ❌ {issue['error']}")
                    else:
                        print(f"   📍 第{issue['line']}行: {issue['content']}")
            else:
                print("✅ 未发现敏感信息")
    
    print(f"\n📊 检查完成，共发现 {len(all_issues)} 个问题")
    
    if all_issues:
        print("\n🚨 安全建议:")
        print("1. 将真实的access_key、token等敏感信息放入环境变量")
        print("2. 使用示例配置文件，不要将真实配置提交到代码仓库")
        print("3. 确保.gitignore文件包含了所有敏感文件")
        print("4. 在提交前运行此脚本进行检查")
        return 1
    else:
        print("\n✅ 未发现安全问题，可以安全提交")
        return 0


if __name__ == '__main__':
    sys.exit(main())