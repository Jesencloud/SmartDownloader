场景一：下载 urls.txt 中的视频 (默认模式)
这是最基础的用法，它会读取 urls.txt 文件，并为其中的每个链接下载**视频(MP4)**和官方字幕。

Bash

python main.py urls.txt -b
python main.py: 运行主程序。

urls.txt: 这是您要处理的输入文件。

-b (或 --batch-file): 告诉脚本，前面的urls.txt是一个包含URL列表的文件，而不是一个视频链接。

场景二：批量提取 urls.txt 中所有视频的音频 (MP3)
如果您只想要音频文件。

Bash

python main.py urls.txt -b --mode audio (video)
--mode audio (或 -m audio): 指定了下载模式为“仅音频”。

场景三：批量下载视频(MP4)和独立的音频文件(MP3)
如果您希望每个视频都同时拥有一个MP4和一个MP3文件。

Bash

python main.py urls.txt -b --mode both
--mode both: 指定下载模式为“两者都要”。

场景四：【最强模式】批量下载并启用AI字幕生成
这是功能全开的模式。它会批量处理urls.txt，下载视频和音频，并且在视频没有官方字幕的情况下，自动为您生成AI字幕。

Bash
lsof -i -P | grep LISTEN
python main.py urls.txt -b --mode both --ai-subs --proxy socks5://127.0.0.1:1082
python main.py [您的URL或文件名] [其他参数] --proxy http://127.0.0.1:1082
运行新命令: 在终端中，使用 --translate-file 参数，后面跟上您的文件名或路径。

Bash


# 如果文件就在当前文件夹
python main.py --translate-file "001_T....en.srt"
# 您也可以提供一个绝对路径
python main.py --translate-file "/path/to/your/file.en.srt"


--ai-subs: 开启“AI字幕生成”功能的开关。

执行这个命令后，脚本会逐一处理文件中的链接。对于每个链接，它会先下载视频和音频。下载完成后，如果发现该视频没有附带任何.srt字幕文件，它就会自动启动Whisper进行语音识别，然后翻译并合并字幕。

请记住：启用--ai-subs的流程会消耗更多的时间和计算资源，请耐心等待。



对于您的 M4 Mac mini，我们有两种直观且可靠的方法来测试 whisper-cpp（通过 whisper-cli 命令）是否已经用上了 Apple Silicon 的硬件加速。

方法一：查看 whisper-cli 的启动日志（最精确）
这是最直接、最准确的方法。whisper-cli 在启动时会打印详细的初始化信息，我们只需查看其中是否包含特定关键字即可。

准备一个音频文件: 找到之前任意一个下载好的 .mp3 文件。

直接在终端中运行: 打开“终端”应用，输入以下命令（请将末尾的路径替换为您真实的MP3文件路径，可以直接将文件拖拽到终端窗口来获取路径）：

Bash

whisper-cli --model ~/.cache/whisper/whisper.cpp/ggml-base.en.bin --language en "/Users/jiantai/Documents/script/SmartDownloader/20250709-034808/001_Texas-floods-death-toll-climbs-to-at-least-107...mp3"
观察输出: 在转录结果出现之前，您会看到一段初始化信息。请在其中寻找以下关键标志：

✅ use gpu = 1：这表示程序决定启用GPU。

✅ whisper_backend_init_gpu: using Metal backend：这是决定性证据，表明正在使用苹果的 Metal 加速框架。

✅ ggml_metal_init: found device: Apple M4：确认找到了您的 M4芯片。

✅ ggml_metal_init: GPU name: Apple M4：确认将使用 M4的GPU 进行计算。

只要您在日志中看到了包含 Metal 和 Apple M4 的字样，就可以100%确定硬件加速已经成功开启。根据您之前提供给我的成功日志，您的设置是完全正确的。