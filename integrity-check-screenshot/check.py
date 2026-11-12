import os
import re

def find_missing_numbers(folder_path):
    # 获取文件夹中的所有文件名
    files = os.listdir(folder_path)
    
    file_numbers = []
    for file in files:
        # 跳过子文件夹
        if os.path.isdir(os.path.join(folder_path, file)):
            continue
            
        # 匹配文件名开头的数字（例如 "1 示例市..." 中的 1）
        match = re.match(r'^\s*(\d+)', file)
        if match:
            file_numbers.append(int(match.group(1)))

    if not file_numbers:
        print("未在文件名开头找到任何编号！")
        return

    # 去重并排序
    unique_numbers = sorted(list(set(file_numbers)))
    start_num = unique_numbers[0]
    end_num = unique_numbers[-1]

    # 计算缺失的编号
    full_set = set(range(start_num, end_num + 1))
    missing_numbers = sorted(list(full_set - set(unique_numbers)))

    # 输出结果
    print(f"扫描范围：{start_num} ~ {end_num}")
    print(f"实际存在文件数：{len(unique_numbers)}")
    if missing_numbers:
        print(f"⚠️ 发现中断/缺失的编号 ({len(missing_numbers)} 个):")
        print(missing_numbers)
    else:
        print("✅ 编号连续，没有缺失！")

# --- 使用说明 ---
# 将下面的路径替换为你实际要检查的文件夹路径
target_folder = r"backups/demo"

if __name__ == "__main__":
    find_missing_numbers(target_folder)