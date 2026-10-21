# 源服务器VLM配置文件

`configuration_internvl_chat.py` 是原实验所用 `ReCogDrive-VLM-2B` 目录中的原字节副本，4,409字节；本次补传未修改模型代码，也未改动验收指纹。

SHA256：`e68305f4777a07f19b747c5034d9cf13be62ccd504c14aba0e0320c1d5f032fb`。

该值与根目录及冻结研究配置 `repair_final_baseline.json` 中的 `vlm_sha256` 一致。此前版本只携带了指纹，没有携带这个源文件，因此目标机使用另一份VLM配置代码时会在模型验收处失败。

本文件包括 `InternVisionConfig`／`LlamaConfig`／`Qwen2Config` 的创建逻辑，以及创建配置失败时输出异常和traceback的诊断包装。要确认目标机文件具体改了哪些行，可在覆盖前执行 `diff -u /你的VLM目录/configuration_internvl_chat.py assets/vlm_source/configuration_internvl_chat.py`。

在仓库根目录执行以下步骤。先确认 `paths.continuation.local.json` 中的 `vlm` 指向目标机准备使用的模型目录。代码会先备份旧文件，再安装源版本；已有正确文件时直接跳过。

```bash
git pull --ff-only
python -B - <<'PY'
import hashlib
import json
import shutil
from pathlib import Path

name = 'configuration_internvl_chat.py'
source = Path('assets/vlm_source') / name
expected = json.loads(Path('configs/repair_final_baseline.json').read_text())['vlm_sha256'][name]
data = source.read_bytes()
assert hashlib.sha256(data).hexdigest() == expected, '仓库源文件指纹不符'
vlm = Path(json.loads(Path('paths.continuation.local.json').read_text())['vlm']).expanduser()
assert vlm.is_dir(), 'VLM目录不存在'
target = vlm / name
old = target.read_bytes() if target.exists() else None
if old == data:
    print('文件已经匹配，无需替换:', target)
else:
    if old is not None:
        old_sha = hashlib.sha256(old).hexdigest()
        backup = vlm / (name + '.before-portable-' + old_sha + '.bak')
        if backup.exists():
            assert backup.read_bytes() == old, '备份内容不符'
        else:
            backup.write_bytes(old)
        print('旧文件已备份:', backup)
    shutil.copyfile(source, target)
    assert hashlib.sha256(target.read_bytes()).hexdigest() == expected
    print('源文件已安装:', target, expected)
PY
```

随后重新执行模型验收，`workspace`替换为之前prepare所用的实际目录：

```bash
python -B -m continuation.doctor --paths paths.continuation.local.json \
  --workspace /data/recogdrive-run --models-only
```

后续验证请新启动Python进程，以加载替换后的模型配置代码。
