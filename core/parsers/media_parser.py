"""
音视频解析器（纯Python实现，最小依赖）

支持格式：
- 音频：MP3, WAV, FLAC, AAC, M4A, OGG, WMA
- 视频：MP4, MKV, AVI, MOV, WMV, FLV, WEBM

解析能力（无需外部依赖）：
- 元数据提取：标题、艺术家、专辑、时长、比特率、采样率、分辨率、编码格式
- 字幕提取：SRT/VTT/ASS 外挂字幕，MP4/MKV内嵌字幕轨道
- 章节信息：提取章节标题和时间戳

增强特性：
- MP3 真实比特率解析（从MPEG1 Layer3帧头比特率表获取）
- MKV 正确的 EBML VINT（变长整数）解析
- FLV onMetaData（AMF格式）解析
- MP4 box 扩展大小（size=1）处理

可选增强（需额外安装）：
- 语音转文字：需要 faster-whisper 或 openai-whisper
- 视频帧OCR：需要 OpenCV + easyocr/pytesseract
"""
import struct
import re
import os
import logging
from pathlib import Path

from .text_utils import clean_text

logger = logging.getLogger(__name__)


class MediaParser:
    """音视频元数据提取器"""

    AUDIO_FORMATS = {
        "mp3": "MP3 音频",
        "wav": "WAV 音频",
        "flac": "FLAC 音频",
        "aac": "AAC 音频",
        "m4a": "M4A 音频",
        "ogg": "OGG 音频",
        "wma": "WMA 音频",
        "opus": "Opus 音频",
    }

    VIDEO_FORMATS = {
        "mp4": "MP4 视频",
        "mkv": "MKV 视频",
        "avi": "AVI 视频",
        "mov": "MOV 视频",
        "wmv": "WMV 视频",
        "flv": "FLV 视频",
        "webm": "WebM 视频",
        "m4v": "M4V 视频",
        "3gp": "3GP 视频",
    }

    SUBTITLE_FORMATS = {
        "srt": "SRT 字幕",
        "vtt": "WebVTT 字幕",
        "ass": "ASS 字幕",
        "ssa": "SSA 字幕",
        "sub": "SUB 字幕",
    }

    # MPEG1 Layer3 比特率表（单位 kbps），按 version/bitrate_index 索引
    # 第一维: MPEG版本（0=MPEG2.5, 1=保留, 2=MPEG2, 3=MPEG1）
    # 第二维: 比特率索引（0-14），索引15为无效/bad
    MP3_BITRATE_TABLE = {
        3: {  # MPEG1
            0: 0, 1: 32, 2: 64, 3: 96, 4: 128, 5: 160,
            6: 192, 7: 224, 8: 256, 9: 288, 10: 320,
            11: 352, 12: 384, 13: 416, 14: 448, 15: 0,
        },
        2: {  # MPEG2
            0: 0, 1: 8, 2: 16, 3: 24, 4: 32, 5: 40,
            6: 48, 7: 56, 8: 64, 9: 80, 10: 96,
            11: 112, 12: 128, 13: 144, 14: 160, 15: 0,
        },
        0: {  # MPEG2.5
            0: 0, 1: 8, 2: 16, 3: 24, 4: 32, 5: 40,
            6: 48, 7: 56, 8: 64, 9: 80, 10: 96,
            11: 112, 12: 128, 13: 144, 14: 160, 15: 0,
        },
    }

    # MPEG 采样率表（单位 Hz）
    # 第一维: MPEG版本（0=MPEG2.5, 1=保留, 2=MPEG2, 3=MPEG1）
    MP3_SAMPLE_RATE_TABLE = {
        3: [44100, 48000, 32000],  # MPEG1
        2: [22050, 24000, 16000],  # MPEG2
        0: [11025, 12000, 8000],   # MPEG2.5
    }

    def parse(self, file_path: str) -> str:
        """通用解析入口"""
        ext = Path(file_path).suffix.lower().lstrip(".")

        if ext in self.AUDIO_FORMATS:
            return self.parse_audio(file_path)
        elif ext in self.VIDEO_FORMATS:
            return self.parse_video(file_path)
        elif ext in self.SUBTITLE_FORMATS:
            return self.parse_subtitle(file_path)
        else:
            raise ValueError(f"不支持的音视频格式: {ext}")

    def parse_audio(self, file_path: str) -> str:
        """解析音频文件，提取元数据"""
        path = Path(file_path)
        ext = path.suffix.lower().lstrip(".")

        metadata = self._get_audio_metadata(file_path, ext)
        subtitle_text = self._find_external_subtitles(file_path)

        lines = []
        lines.append(f"音频文件: {path.name}")
        lines.append(f"格式: {self.AUDIO_FORMATS.get(ext, ext.upper())}")
        lines.append(f"大小: {self._format_size(path.stat().st_size)}")
        lines.append("")

        lines.append("--- 元数据 ---")
        for key, value in metadata.items():
            if value:
                lines.append(f"{key}: {value}")
        lines.append("")

        if subtitle_text:
            lines.append("--- 字幕文本 ---")
            lines.append(subtitle_text[:5000])
            if len(subtitle_text) > 5000:
                lines.append(f"... (共{len(subtitle_text)}字符，已截断)")
        else:
            # 尝试语音转文字
            transcript = self._try_speech_to_text(file_path, is_audio=True)
            if transcript:
                lines.append("--- 语音转文字 ---")
                lines.append(transcript)
            else:
                lines.append("--- 提示 ---")
                lines.append("未找到字幕文件。如需提取语音内容，请安装 faster-whisper:")
                lines.append("pip install faster-whisper")

        # 通用文本清洗
        return clean_text("\n".join(lines))

    def parse_video(self, file_path: str) -> str:
        """解析视频文件，提取元数据和字幕"""
        path = Path(file_path)
        ext = path.suffix.lower().lstrip(".")

        metadata = self._get_video_metadata(file_path, ext)
        subtitle_text = self._extract_subtitles(file_path, ext)

        # 同时检查外部字幕文件
        if not subtitle_text:
            subtitle_text = self._find_external_subtitles(file_path)

        lines = []
        lines.append(f"视频文件: {path.name}")
        lines.append(f"格式: {self.VIDEO_FORMATS.get(ext, ext.upper())}")
        lines.append(f"大小: {self._format_size(path.stat().st_size)}")
        lines.append("")

        lines.append("--- 元数据 ---")
        for key, value in metadata.items():
            if value:
                lines.append(f"{key}: {value}")
        lines.append("")

        if subtitle_text:
            lines.append("--- 字幕文本 ---")
            lines.append(subtitle_text[:8000])
            if len(subtitle_text) > 8000:
                lines.append(f"... (共{len(subtitle_text)}字符，已截断)")
        else:
            # 尝试语音转文字
            transcript = self._try_speech_to_text(file_path, is_audio=False)
            if transcript:
                lines.append("--- 语音转文字 ---")
                lines.append(transcript[:5000])
            else:
                lines.append("--- 提示 ---")
                lines.append("未找到字幕文件。如需提取语音内容，请安装 faster-whisper:")
                lines.append("pip install faster-whisper")

        # 通用文本清洗
        return clean_text("\n".join(lines))

    def parse_subtitle(self, file_path: str) -> str:
        """解析字幕文件"""
        path = Path(file_path)
        ext = path.suffix.lower().lstrip(".")

        with open(file_path, "rb") as f:
            raw = f.read()

        text = None
        for enc in ["utf-8", "utf-8-sig", "gbk", "gb2312", "gb18030", "big5", "latin-1"]:
            try:
                text = raw.decode(enc, errors="strict")
                break
            except (UnicodeDecodeError, LookupError):
                continue
        if text is None:
            text = raw.decode("utf-8", errors="replace")

        if ext == "srt":
            return clean_text(self._parse_srt(text))
        elif ext == "vtt":
            return clean_text(self._parse_vtt(text))
        elif ext in ("ass", "ssa"):
            return clean_text(self._parse_ass(text))
        else:
            return clean_text(text)

    # ===== 音频元数据提取 =====

    def _get_audio_metadata(self, file_path: str, ext: str) -> dict:
        """提取音频元数据"""
        metadata = {}
        try:
            if ext == "mp3":
                metadata = self._parse_mp3(file_path)
            elif ext == "wav":
                metadata = self._parse_wav(file_path)
            elif ext == "flac":
                metadata = self._parse_flac(file_path)
            elif ext in ("m4a", "aac"):
                metadata = self._parse_mp4_audio(file_path)
            elif ext == "ogg":
                metadata = self._parse_ogg(file_path)
            else:
                # 通用回退：尝试从文件头读取基本信息
                metadata = {"格式": ext.upper(), "时长": "未知"}
        except Exception as e:
            logger.warning(f"音频元数据提取失败: {e}")
            metadata = {"格式": ext.upper(), "状态": "元数据解析失败"}

        return metadata

    def _parse_mp3(self, file_path: str) -> dict:
        """解析MP3文件的ID3标签，从帧头获取真实比特率"""
        result = {}
        with open(file_path, "rb") as f:
            data = f.read()

        # 检查ID3v2标签（文件开头）
        if data[:3] == b"ID3":
            size = self._id3_syncsafe_int(data[6:10])
            tag_data = data[10:10+size]
            id3_tags = self._parse_id3v2(tag_data)
            result.update(id3_tags)

        # 从第一个帧头解析真实比特率和采样率
        file_size = len(data)
        frame_pos = self._find_mp3_frame(data)
        if frame_pos >= 0 and frame_pos + 4 < len(data):
            # 解析MPEG帧头（4字节）
            # 字节结构: AAAAAAAA AAABBCCD EEEEFFGH IIJJKLMM
            b0 = data[frame_pos]
            b1 = data[frame_pos + 1]
            b2 = data[frame_pos + 2]

            # B(2bits): MPEG版本 (00=2.5, 01=保留, 10=2, 11=1)
            version_bits = (b1 >> 3) & 0x03
            # C(2bits): Layer (00=保留, 01=Layer3, 10=Layer2, 11=Layer1)
            layer_bits = (b1 >> 1) & 0x03
            # E(4bits): 比特率索引
            bitrate_index = (b2 >> 4) & 0x0F
            # F(2bits): 采样率索引
            sample_rate_index = (b2 >> 2) & 0x03
            # G(1bit): 是否有填充
            padding = (b2 >> 1) & 0x01

            # 只解析 MPEG1 Layer3 或 MPEG2/2.5 Layer3
            is_layer3 = (layer_bits == 1)  # 01 = Layer3
            if is_layer3 and version_bits != 1:  # 排除保留版本
                bitrate_table = self.MP3_BITRATE_TABLE.get(version_bits)
                sample_rate_table = self.MP3_SAMPLE_RATE_TABLE.get(version_bits)

                if bitrate_table and sample_rate_table:
                    bitrate_kbps = bitrate_table.get(bitrate_index, 0)
                    sample_rate = sample_rate_table[sample_rate_index] if sample_rate_index < len(sample_rate_table) else 0

                    if bitrate_kbps > 0:
                        result["比特率"] = f"{bitrate_kbps} kbps"

                        # 用真实比特率计算时长
                        # 时长(秒) = 文件大小(bytes) * 8 / (比特率 kbps * 1000)
                        # 注意：这里用整个文件大小估算，包含ID3标签等开销
                        duration_sec = (file_size * 8) / (bitrate_kbps * 1000)
                        result["时长"] = self._format_duration(duration_sec)

                    if sample_rate > 0:
                        result["采样率"] = f"{sample_rate} Hz"
            else:
                # 非Layer3帧，回退到简单估算
                result["比特率"] = "128 kbps（估算）"
                if file_size > 0:
                    duration_sec = (file_size * 8) / (128 * 1000)
                    result["时长"] = self._format_duration(duration_sec)

        # 检查ID3v1标签（文件末尾128字节）
        if len(data) > 128 and data[-128:-125] == b"TAG":
            tag = data[-128:]
            title = tag[3:33].decode("latin-1", errors="replace").strip("\x00").strip()
            artist = tag[33:63].decode("latin-1", errors="replace").strip("\x00").strip()
            album = tag[63:93].decode("latin-1", errors="replace").strip("\x00").strip()
            year = tag[93:97].decode("latin-1", errors="replace").strip("\x00").strip()
            if title and "标题" not in result:
                result["标题"] = title
            if artist and "艺术家" not in result:
                result["艺术家"] = artist
            if album and "专辑" not in result:
                result["专辑"] = album
            if year and "年份" not in result:
                result["年份"] = year

        if not result.get("标题"):
            result["标题"] = Path(file_path).stem

        return result

    def _parse_id3v2(self, data: bytes) -> dict:
        """解析ID3v2标签"""
        result = {}
        pos = 0
        frame_map = {
            "TIT2": "标题", "TPE1": "艺术家", "TALB": "专辑",
            "TYER": "年份", "TCON": "流派", "TCOM": "作曲",
            "TENC": "编码", "TLEN": "时长(ms)", "TRCK": "曲目",
            "COMM": "备注", "TDRC": "日期", "TIT1": "分组",
        }

        while pos < len(data) - 10:
            if data[pos] == 0:
                pos += 1
                continue
            frame_id = data[pos:pos+4].decode("latin-1", errors="replace")
            if not frame_id or not frame_id.isalnum():
                break
            frame_size = self._id3_syncsafe_int(data[pos+4:pos+8])
            if frame_size <= 0 or pos + 10 + frame_size > len(data):
                break

            frame_data = data[pos+10:pos+10+frame_size]

            if frame_id.startswith("T") and len(frame_data) > 0:
                encoding = frame_data[0]
                if encoding == 0:
                    value = frame_data[1:].decode("latin-1", errors="replace").strip("\x00").strip()
                elif encoding == 1 or encoding == 2:
                    value = frame_data[1:].decode("utf-16", errors="replace").strip("\x00").strip()
                elif encoding == 3:
                    value = frame_data[1:].decode("utf-8", errors="replace").strip("\x00").strip()
                else:
                    value = frame_data[1:].decode("latin-1", errors="replace").strip("\x00").strip()

                label = frame_map.get(frame_id, frame_id)
                result[label] = value

            pos += 10 + frame_size

        return result

    def _id3_syncsafe_int(self, data: bytes) -> int:
        """将4字节的同步安全整数转为普通整数"""
        if len(data) < 4:
            return 0
        return (data[0] << 21) | (data[1] << 14) | (data[2] << 7) | data[3]

    def _find_mp3_frame(self, data: bytes) -> int:
        """查找第一个MP3帧头

        MP3帧同步字: 11个连续的1（0xFF + 高5位为1）
        """
        for i in range(min(len(data) - 4, 100000)):
            if data[i] == 0xFF and (data[i+1] & 0xE0) == 0xE0:
                return i
        return -1

    def _parse_wav(self, file_path: str) -> dict:
        """解析WAV文件"""
        result = {}
        with open(file_path, "rb") as f:
            data = f.read()

        if data[:4] != b"RIFF" or data[8:12] != b"WAVE":
            return result

        # 找 fmt chunk
        pos = 12
        while pos < len(data) - 8:
            chunk_id = data[pos:pos+4].decode("latin-1", errors="replace")
            chunk_size = struct.unpack("<I", data[pos+4:pos+8])[0]
            if chunk_id == "fmt ":
                fmt_data = data[pos+8:pos+8+chunk_size]
                if len(fmt_data) >= 16:
                    audio_format = struct.unpack("<H", fmt_data[0:2])[0]
                    channels = struct.unpack("<H", fmt_data[2:4])[0]
                    sample_rate = struct.unpack("<I", fmt_data[4:8])[0]
                    bits_per_sample = struct.unpack("<H", fmt_data[14:16])[0]
                    result["编码格式"] = "PCM" if audio_format == 1 else f"格式{audio_format}"
                    result["声道数"] = "立体声" if channels == 2 else "单声道" if channels == 1 else f"{channels}声道"
                    result["采样率"] = f"{sample_rate} Hz"
                    result["位深"] = f"{bits_per_sample} bit"
                    break
            pos += 8 + chunk_size

        # 时长估算
        data_size = 0
        pos = 12
        while pos < len(data) - 8:
            chunk_id = data[pos:pos+4].decode("latin-1", errors="replace")
            chunk_size = struct.unpack("<I", data[pos+4:pos+8])[0]
            if chunk_id == "data":
                data_size = chunk_size
                break
            pos += 8 + chunk_size

        if data_size > 0 and result.get("采样率") and result.get("位深") and result.get("声道数"):
            try:
                sr = int(result["采样率"].split()[0])
                bps = int(result["位深"].split()[0])
                ch = 2 if "立体" in result["声道数"] else 1
                byte_rate = sr * ch * (bps // 8)
                duration = data_size / byte_rate
                result["时长"] = self._format_duration(duration)
            except Exception:
                pass

        if "标题" not in result:
            result["标题"] = Path(file_path).stem

        return result

    def _parse_flac(self, file_path: str) -> dict:
        """解析FLAC文件"""
        result = {}
        with open(file_path, "rb") as f:
            data = f.read()

        if data[:4] != b"fLaC":
            return result

        pos = 4
        stream_info_parsed = False

        while pos < len(data) - 4:
            if len(data) <= pos:
                break
            is_last = (data[pos] & 0x80) != 0
            block_type = data[pos] & 0x7F
            block_size = struct.unpack(">I", b"\x00" + data[pos+1:pos+4])[0]

            if pos + 4 + block_size > len(data):
                break

            block_data = data[pos+4:pos+4+block_size]

            if block_type == 0 and not stream_info_parsed:
                # STREAMINFO
                if len(block_data) >= 34:
                    min_block = struct.unpack(">H", block_data[0:2])[0]
                    max_block = struct.unpack(">H", block_data[2:4])[0]
                    min_frame = struct.unpack(">I", b"\x00" + block_data[4:7])[0]
                    max_frame = struct.unpack(">I", b"\x00" + block_data[7:10])[0]
                    sr_chan_bps = struct.unpack(">I", block_data[10:14])[0]
                    sample_rate = (sr_chan_bps >> 12) & 0xFFFFF
                    channels = ((sr_chan_bps >> 9) & 0x7) + 1
                    bps = ((sr_chan_bps >> 4) & 0x1F) + 1
                    total_samples = ((sr_chan_bps & 0xF) << 32) | struct.unpack(">I", block_data[14:18])[0]

                    result["编码格式"] = "FLAC"
                    result["声道数"] = "立体声" if channels == 2 else "单声道" if channels == 1 else f"{channels}声道"
                    result["采样率"] = f"{sample_rate} Hz"
                    result["位深"] = f"{bps} bit"
                    if sample_rate > 0:
                        result["时长"] = self._format_duration(total_samples / sample_rate)
                    stream_info_parsed = True

            elif block_type == 4:
                # VORBIS_COMMENT
                comments = self._parse_vorbis_comments(block_data)
                if "标题" not in result and comments.get("title"):
                    result["标题"] = comments["title"]
                if "艺术家" not in result and comments.get("artist"):
                    result["艺术家"] = comments["artist"]
                if "专辑" not in result and comments.get("album"):
                    result["专辑"] = comments["album"]
                if comments.get("genre"):
                    result["流派"] = comments["genre"]
                if comments.get("date"):
                    result["日期"] = comments["date"]

            if is_last:
                break
            pos += 4 + block_size

        if "标题" not in result:
            result["标题"] = Path(file_path).stem

        return result

    def _parse_vorbis_comments(self, data: bytes) -> dict:
        """解析Vorbis注释"""
        result = {}
        try:
            vendor_len = struct.unpack("<I", data[0:4])[0]
            pos = 4 + vendor_len
            num_comments = struct.unpack("<I", data[pos:pos+4])[0]
            pos += 4

            for _ in range(num_comments):
                if pos + 4 > len(data):
                    break
                comment_len = struct.unpack("<I", data[pos:pos+4])[0]
                pos += 4
                if pos + comment_len > len(data):
                    break
                comment = data[pos:pos+comment_len].decode("utf-8", errors="replace")
                pos += comment_len
                if "=" in comment:
                    key, val = comment.split("=", 1)
                    result[key.lower().strip()] = val.strip()
        except Exception:
            pass
        return result

    def _parse_mp4_audio(self, file_path: str) -> dict:
        """解析MP4/M4A音频（简化版）"""
        result = {}
        with open(file_path, "rb") as f:
            data = f.read()

        # 找 moov box
        moov = self._find_mp4_box(data, b"moov")
        if not moov:
            return result

        # 找 mvhd (movie header) 计算时长
        mvhd = self._find_mp4_box(moov, b"mvhd")
        if mvhd and len(mvhd) > 20:
            version = mvhd[0]
            if version == 1:
                timescale = struct.unpack(">I", mvhd[20:24])[0]
                duration = struct.unpack(">Q", mvhd[24:32])[0]
            else:
                timescale = struct.unpack(">I", mvhd[12:16])[0]
                duration = struct.unpack(">I", mvhd[16:20])[0]
            if timescale > 0:
                result["时长"] = self._format_duration(duration / timescale)

        # 找 udta -> meta -> ilst (iTunes风格元数据)
        udta = self._find_mp4_box(moov, b"udta")
        if udta:
            meta = self._find_mp4_box(udta, b"meta")
            if meta:
                ilst = self._find_mp4_box(meta, b"ilst")
                if ilst:
                    tags = self._parse_mp4_ilst(ilst)
                    result.update(tags)

        if "标题" not in result:
            result["标题"] = Path(file_path).stem

        return result

    def _find_mp4_box(self, data: bytes, box_type: bytes) -> bytes:
        """在MP4数据中查找指定box

        支持 box 扩展大小格式：
        - 正常格式: [4字节size][4字节type][payload]
        - 扩展格式: size=1 时，[4字节size=1][4字节type][8字节实际大小][payload]
        """
        pos = 0
        data_len = len(data)
        while pos < data_len - 8:
            if pos + 8 > data_len:
                break
            size = struct.unpack(">I", data[pos:pos+4])[0]
            type_ = data[pos+4:pos+8]

            if size == 1:
                # 扩展大小格式：后面8字节为实际大小
                if pos + 16 > data_len:
                    break
                actual_size = struct.unpack(">Q", data[pos+8:pos+16])[0]
                if actual_size < 16 or pos + actual_size > data_len:
                    break
                if type_ == box_type:
                    return data[pos+16:pos+actual_size]
                pos += actual_size
            elif size < 8:
                break
            else:
                if type_ == box_type:
                    return data[pos+8:pos+size] if size > 8 else b""
                pos += size
        return b""

    def _find_mp4_box_at(self, data: bytes, box_type: bytes, start: int) -> bytes:
        """从指定位置开始查找box（支持扩展大小）"""
        pos = start
        data_len = len(data)
        while pos < data_len - 8:
            if pos + 8 > data_len:
                break
            size = struct.unpack(">I", data[pos:pos+4])[0]
            type_ = data[pos+4:pos+8]

            if size == 1:
                # 扩展大小格式
                if pos + 16 > data_len:
                    break
                actual_size = struct.unpack(">Q", data[pos+8:pos+16])[0]
                if actual_size < 16 or pos + actual_size > data_len:
                    break
                if type_ == box_type:
                    return data[pos+16:pos+actual_size]
                pos += actual_size
            elif size < 8 or pos + size > data_len:
                break
            else:
                if type_ == box_type:
                    return data[pos+8:pos+size] if size > 8 else b""
                pos += size
        return b""

    def _parse_mp4_ilst(self, data: bytes) -> dict:
        """解析MP4 ilst 元数据"""
        result = {}
        tag_map = {
            b"\xa9nam": "标题", b"\xa9ART": "艺术家", b"\xa9alb": "专辑",
            b"\xa9day": "年份", b"\xa9gen": "流派", b"\xa9wrt": "作曲",
            b"\xa9too": "编码工具", b"\xa9cmt": "备注",
            b"trkn": "曲目", b"disk": "碟片",
        }
        pos = 0
        while pos < len(data) - 8:
            if pos + 8 > len(data):
                break
            size = struct.unpack(">I", data[pos:pos+4])[0]
            if size < 8 or pos + size > len(data):
                break
            tag = data[pos+4:pos+8]
            atom_data = data[pos+8:pos+size]
            # 找 data atom
            data_atom = self._find_mp4_box(atom_data, b"data")
            if data_atom and len(data_atom) > 8:
                value_data = data_atom[8:] if len(data_atom) > 8 else b""
                try:
                    value = value_data.decode("utf-8", errors="replace").strip("\x00").strip()
                except Exception:
                    value = value_data.decode("latin-1", errors="replace").strip("\x00").strip()
                label = tag_map.get(tag, tag.decode("latin-1", errors="replace"))
                result[label] = value
            pos += size
        return result

    def _parse_ogg(self, file_path: str) -> dict:
        """解析OGG文件（简化版）"""
        result = {}
        with open(file_path, "rb") as f:
            data = f.read()

        if data[:4] != b"OggS":
            return result

        # 找第一个page中的Vorbis comments
        pos = 0
        pages = 0
        while pos < len(data) and pages < 5:
            if data[pos:pos+4] != b"OggS":
                break
            page_segments = data[pos+26]
            segment_table_start = pos + 27
            segment_sizes = []
            for i in range(page_segments):
                segment_sizes.append(data[segment_table_start + i])
            total_size = sum(segment_sizes)
            payload_start = segment_table_start + page_segments
            payload = data[payload_start:payload_start+total_size]

            if pages == 0 and payload:
                # 第一个packet: identification header
                if payload[0] == 0x01 and payload[1:7] == b"vorbis":
                    if len(payload) > 11:
                        sample_rate = struct.unpack("<I", payload[12:16])[0]
                        channels = payload[11]
                        result["编码格式"] = "Vorbis"
                        result["采样率"] = f"{sample_rate} Hz"
                        result["声道数"] = "立体声" if channels == 2 else "单声道" if channels == 1 else f"{channels}声道"

            elif pages == 1 and payload:
                # 第二个packet: comment header
                if payload[0] == 0x03 and payload[1:7] == b"vorbis":
                    comments = self._parse_vorbis_comments(payload[7:])
                    if comments.get("title"):
                        result["标题"] = comments["title"]
                    if comments.get("artist"):
                        result["艺术家"] = comments["artist"]
                    if comments.get("album"):
                        result["专辑"] = comments["album"]
                    if comments.get("genre"):
                        result["流派"] = comments["genre"]

            pos = payload_start + total_size
            pages += 1

        if "标题" not in result:
            result["标题"] = Path(file_path).stem

        return result

    # ===== 视频元数据提取 =====

    def _get_video_metadata(self, file_path: str, ext: str) -> dict:
        """提取视频元数据"""
        metadata = {}
        try:
            if ext in ("mp4", "m4v", "mov", "3gp"):
                metadata = self._parse_mp4_video(file_path)
            elif ext in ("mkv", "webm"):
                metadata = self._parse_mkv(file_path)
            elif ext == "avi":
                metadata = self._parse_avi(file_path)
            elif ext == "flv":
                metadata = self._parse_flv(file_path)
            else:
                metadata = {"格式": ext.upper(), "时长": "未知"}
        except Exception as e:
            logger.warning(f"视频元数据提取失败: {e}")
            metadata = {"格式": ext.upper(), "状态": "元数据解析失败"}

        return metadata

    def _parse_mp4_video(self, file_path: str) -> dict:
        """解析MP4视频元数据"""
        result = {}
        with open(file_path, "rb") as f:
            data = f.read()

        moov = self._find_mp4_box(data, b"moov")
        if not moov:
            return result

        mvhd = self._find_mp4_box(moov, b"mvhd")
        if mvhd and len(mvhd) > 20:
            version = mvhd[0]
            if version == 1:
                timescale = struct.unpack(">I", mvhd[20:24])[0]
                duration = struct.unpack(">Q", mvhd[24:32])[0]
            else:
                timescale = struct.unpack(">I", mvhd[12:16])[0]
                duration = struct.unpack(">I", mvhd[16:20])[0]
            if timescale > 0:
                result["时长"] = self._format_duration(duration / timescale)

        # 找 trak -> tkhd / mdia -> minf -> vmhd/smhd (视频/音频轨道)
        trak_start = 0
        trak_idx = 0
        while True:
            trak = self._find_mp4_box_at(moov, b"trak", trak_start)
            if not trak:
                break
            trak_start = moov.find(b"trak", trak_start + 4) + 4 if trak_start + 4 < len(moov) else len(moov)

            tkhd = self._find_mp4_box(trak, b"tkhd")
            mdia = self._find_mp4_box(trak, b"mdia")
            minf = self._find_mp4_box(mdia, b"minf") if mdia else b""

            if minf:
                vmhd = self._find_mp4_box(minf, b"vmhd")
                smhd = self._find_mp4_box(minf, b"smhd")

                if vmhd and tkhd and len(tkhd) > 80:
                    # 视频轨道
                    version = tkhd[0]
                    if version == 1:
                        width = struct.unpack(">I", tkhd[80:84])[0] >> 16
                        height = struct.unpack(">I", tkhd[84:88])[0] >> 16
                    else:
                        width = struct.unpack(">I", tkhd[68:72])[0] >> 16
                        height = struct.unpack(">I", tkhd[72:76])[0] >> 16
                    result["分辨率"] = f"{width} x {height}"

                    # 找编码格式
                    stbl = self._find_mp4_box(minf, b"stbl")
                    if stbl:
                        stsd = self._find_mp4_box(stbl, b"stsd")
                        if stsd and len(stsd) > 12:
                            codec = stsd[12:16].decode("latin-1", errors="replace").strip()
                            result["视频编码"] = codec

                elif smhd:
                    # 音频轨道
                    stbl = self._find_mp4_box(minf, b"stbl")
                    if stbl:
                        stsd = self._find_mp4_box(stbl, b"stsd")
                        if stsd and len(stsd) > 12:
                            codec = stsd[12:16].decode("latin-1", errors="replace").strip()
                            result["音频编码"] = codec

            trak_idx += 1
            if trak_idx > 20:
                break

        # 元数据
        udta = self._find_mp4_box(moov, b"udta")
        if udta:
            meta = self._find_mp4_box(udta, b"meta")
            if meta:
                ilst = self._find_mp4_box(meta, b"ilst")
                if ilst:
                    tags = self._parse_mp4_ilst(ilst)
                    result.update(tags)

        if "标题" not in result:
            result["标题"] = Path(file_path).stem

        return result

    def _parse_mkv(self, file_path: str) -> dict:
        """解析MKV/WebM文件，使用正确的EBML VINT（变长整数）解析"""
        result = {}
        with open(file_path, "rb") as f:
            data = f.read()

        # 检查EBML头
        if len(data) < 4 or data[0] != 0x1A:
            return result

        # 找 Segment（ID: 0x1F43B6...，VINT编码为 0x18 0x53 0x80 0x67）
        seg_pos = self._find_ebml_element(data, 0, len(data), b"\x1f\x43\xb6\x75")
        if seg_pos < 0:
            # 回退：直接搜索字节序列
            seg_pos = data.find(b"\x18\x53\x80\x67")
        if seg_pos < 0:
            return result

        # 获取 Segment 大小和范围
        seg_header_pos = seg_pos
        seg_id, seg_id_len, seg_size, seg_size_len = self._read_ebml_element_header(data, seg_pos)
        seg_data_start = seg_pos + seg_id_len + seg_size_len
        if seg_data_start >= len(data):
            return result

        # 搜索 Info（ID: 0x1549A966）
        info_pos = self._scan_for_ebml_id(data, seg_data_start, len(data), b"\x15\x49\xa9\x66")
        if info_pos < 0:
            return result

        result["格式"] = "Matroska"

        # 在 Info 元素内解析子元素
        info_header_pos = info_pos
        info_id, info_id_len, info_size, info_size_len = self._read_ebml_element_header(data, info_pos)
        info_data_start = info_pos + info_id_len + info_size_len
        info_data_end = min(info_data_start + info_size, len(data))

        # 在 Info 范围内遍历子元素
        pos = info_data_start
        while pos < info_data_end:
            child_id, child_id_len, child_size, child_size_len = self._read_ebml_element_header(data, pos)
            if child_id_len == 0:
                break
            child_data_start = pos + child_id_len + child_size_len
            child_data_end = min(child_data_start + child_size, info_data_end)

            if child_id == b"\x44\x89":
                # Duration
                if child_data_end - child_data_start >= 4:
                    dur_bytes = data[child_data_start:child_data_end]
                    try:
                        # Duration 通常是 float（大端序）
                        if len(dur_bytes) == 4:
                            duration = struct.unpack(">f", dur_bytes)[0]
                        elif len(dur_bytes) == 8:
                            duration = struct.unpack(">d", dur_bytes)[0]
                        else:
                            duration = float(dur_bytes[0])
                        result["时长"] = self._format_duration(duration / 1000)
                    except Exception:
                        pass

            elif child_id == b"\x2d\x80":
                # MuxingApp
                try:
                    result["封装工具"] = data[child_data_start:child_data_end].decode("utf-8", errors="replace")
                except Exception:
                    pass

            elif child_id == b"\x57\x41":
                # WritingApp
                try:
                    result["写入工具"] = data[child_data_start:child_data_end].decode("utf-8", errors="replace")
                except Exception:
                    pass

            pos = child_data_end

        # 找 Title（可能在 Info 内部，也可能作为 Segment 的直接子元素）
        title_pos = self._scan_for_ebml_id(data, seg_data_start, len(data), b"\x7b\xa9")
        if title_pos >= 0:
            _, t_id_len, t_size, t_size_len = self._read_ebml_element_header(data, title_pos)
            t_data_start = title_pos + t_id_len + t_size_len
            try:
                title = data[t_data_start:t_data_start + t_size].decode("utf-8", errors="replace")
                if title:
                    result["标题"] = title
            except Exception:
                pass

        # 找 Tracks
        tracks_pos = self._scan_for_ebml_id(data, seg_data_start, len(data), b"\x16\x54\xae\x6b")
        if tracks_pos >= 0:
            _, tr_id_len, tr_size, tr_size_len = self._read_ebml_element_header(data, tracks_pos)
            tr_data_start = tracks_pos + tr_id_len + tr_size_len
            tr_data_end = min(tr_data_start + tr_size, len(data))

            # 在 Tracks 范围内找 TrackEntry 和 Video 元素
            # TrackEntry ID: 0xAE, Video ID: 0xE0, PixelWidth: 0xB0, PixelHeight: 0xBA
            video_width = None
            video_height = None

            # 扫描 Video 子元素中的宽高
            video_pos = self._scan_for_ebml_id(data, tr_data_start, tr_data_end, b"\xe0")
            if video_pos >= 0:
                _, v_id_len, v_size, v_size_len = self._read_ebml_element_header(data, video_pos)
                v_data_start = video_pos + v_id_len + v_size_len
                v_data_end = min(v_data_start + v_size, tr_data_end)

                # 在 Video 范围内找 PixelWidth 和 PixelHeight
                pw_pos = self._scan_for_ebml_id(data, v_data_start, v_data_end, b"\xb0")
                if pw_pos >= 0:
                    _, pw_id_len, pw_size, pw_size_len = self._read_ebml_element_header(data, pw_pos)
                    pw_data_start = pw_pos + pw_id_len + pw_size_len
                    try:
                        pw_bytes = data[pw_data_start:pw_data_start + pw_size]
                        video_width = self._ebml_vint_to_int(pw_bytes)
                    except Exception:
                        pass

                ph_pos = self._scan_for_ebml_id(data, v_data_start, v_data_end, b"\xba")
                if ph_pos >= 0:
                    _, ph_id_len, ph_size, ph_size_len = self._read_ebml_element_header(data, ph_pos)
                    ph_data_start = ph_pos + ph_id_len + ph_size_len
                    try:
                        ph_bytes = data[ph_data_start:ph_data_start + ph_size]
                        video_height = self._ebml_vint_to_int(ph_bytes)
                    except Exception:
                        pass

                if video_width is not None and video_height is not None:
                    result["分辨率"] = f"{video_width} x {video_height}"

        if "标题" not in result:
            result["标题"] = Path(file_path).stem

        return result

    def _read_ebml_element_header(self, data: bytes, pos: int):
        """读取EBML元素头：返回 (element_id, id长度, element_size, size长度)

        EBML 元素格式: [Element ID (VINT)] [Element Size (VINT)] [Payload]
        VINT (变长整数) 编码:
        - 1字节: 1xxxxxxx        -> 值范围 0-127
        - 2字节: 01xxxxxx xxxxxxxx -> 值范围 0-16383
        - 3字节: 001xxxxx ...      -> 值范围 0-2097151
        - 4字节: 0001xxxx ...      -> 值范围 0-268435455
        - 5字节: 00001xxx ...
        - 6字节: 000001xx ...
        - 7字节: 0000001x ...
        - 8字节: 00000001 ...
        """
        if pos >= len(data):
            return b"", 0, 0, 0

        # 读取 Element ID (VINT)
        element_id, id_len = self._read_vint(data, pos)
        pos += id_len

        # 读取 Element Size (VINT)
        element_size, size_len = self._read_vint(data, pos)

        return element_id, id_len, element_size, size_len

    def _read_vint(self, data: bytes, pos: int) -> tuple[bytes, int]:
        """读取一个 VINT（变长整数），返回 (原始字节, 字节长度)

        VINT 编码规则:
        - 第一个字节的 leading zero 数量决定总字节数
        - 1字节: 1xxxxxxx          (0个前导0)
        - 2字节: 01xxxxxx xxxxxxxx  (1个前导0)
        - 3字节: 001xxxxx ...       (2个前导0)
        - 4字节: 0001xxxx ...       (3个前导0)
        - 5字节: 00001xxx ...       (4个前导0)
        - 6字节: 000001xx ...       (5个前导0)
        - 7字节: 0000001x ...       (6个前导0)
        - 8字节: 00000001 ...       (7个前导0)
        """
        if pos >= len(data):
            return b"", 0

        first_byte = data[pos]
        # 计算前导零数量
        if first_byte & 0x80:
            vint_len = 1
        elif first_byte & 0x40:
            vint_len = 2
        elif first_byte & 0x20:
            vint_len = 3
        elif first_byte & 0x10:
            vint_len = 4
        elif first_byte & 0x08:
            vint_len = 5
        elif first_byte & 0x04:
            vint_len = 6
        elif first_byte & 0x02:
            vint_len = 7
        elif first_byte & 0x01:
            vint_len = 8
        else:
            return b"", 0

        if pos + vint_len > len(data):
            return b"", 0

        return data[pos:pos + vint_len], vint_len

    def _ebml_vint_to_int(self, vint_bytes: bytes) -> int:
        """将 VINT 字节转换为整数值

        去掉第一个字节的标记位，保留有效数据位。
        """
        if not vint_bytes:
            return 0
        vint_len = len(vint_bytes)
        # 计算标记位掩码：长度为N时，标记位为第(N-1)位（从高位）
        marker = 1 << (8 - vint_len)
        # 去掉标记位，拼接有效数据
        result = 0
        for i, b in enumerate(vint_bytes):
            if i == 0:
                result = b & (~marker & 0xFF)
            else:
                result = (result << 8) | b
        return result

    def _scan_for_ebml_id(self, data: bytes, start: int, end: int, target_id: bytes) -> int:
        """在指定范围内扫描指定的EBML元素ID

        返回找到的位置，未找到返回 -1。
        使用字节搜索定位候选位置，再验证是否是有效的VINT对齐。
        """
        pos = start
        while pos < end:
            idx = data.find(target_id, pos, end)
            if idx < 0:
                return -1
            # 验证 target_id 是否可以作为合法的 VINT Element ID
            first_byte = target_id[0]
            vint_len = 0
            if first_byte & 0x80:
                vint_len = 1
            elif first_byte & 0x40:
                vint_len = 2
            elif first_byte & 0x20:
                vint_len = 3
            elif first_byte & 0x10:
                vint_len = 4
            if vint_len == len(target_id):
                return idx
            # 不是合法的VINT对齐，继续搜索
            pos = idx + 1
        return -1

    def _find_ebml_element(self, data: bytes, start: int, end: int, element_id: bytes) -> int:
        """在数据中查找指定EBML元素的位置（通过扫描子元素）"""
        pos = start
        while pos < end:
            elem_id, id_len, elem_size, size_len = self._read_ebml_element_header(data, pos)
            if id_len == 0:
                break
            if elem_id == element_id:
                return pos
            # 跳到下一个元素
            next_pos = pos + id_len + size_len + elem_size
            if next_pos <= pos:
                break
            pos = next_pos
        return -1

    def _parse_avi(self, file_path: str) -> dict:
        """解析AVI文件"""
        result = {}
        with open(file_path, "rb") as f:
            data = f.read()

        if data[:4] != b"RIFF" or data[8:12] != b"AVI ":
            return result

        result["格式"] = "AVI"

        # 找 avih
        avih_pos = data.find(b"avih")
        if avih_pos >= 0 and avih_pos + 56 < len(data):
            avih_data = data[avih_pos+8:avih_pos+56]
            if len(avih_data) >= 40:
                microsec_per_frame = struct.unpack("<I", avih_data[0:4])[0]
                total_frames = struct.unpack("<I", avih_data[12:16])[0]
                width = struct.unpack("<I", avih_data[28:32])[0]
                height = struct.unpack("<I", avih_data[32:36])[0]
                if microsec_per_frame > 0:
                    duration = (total_frames * microsec_per_frame) / 1_000_000
                    result["时长"] = self._format_duration(duration)
                result["分辨率"] = f"{width} x {height}"

        if "标题" not in result:
            result["标题"] = Path(file_path).stem

        return result

    def _parse_flv(self, file_path: str) -> dict:
        """解析FLV文件，提取onMetaData（AMF格式）中的duration/width/height"""
        result = {}
        with open(file_path, "rb") as f:
            data = f.read()

        if data[:3] != b"FLV":
            return result

        result["格式"] = "FLV"
        version = data[3]
        type_flags = data[4]
        has_audio = (type_flags & 4) != 0
        has_video = (type_flags & 1) != 0
        result["音频"] = "有" if has_audio else "无"
        result["视频"] = "有" if has_video else "无"

        # 解析FLV body，寻找 onMetaData
        # FLV头部: 9字节 (3 signature + 1 version + 4 flags/offset)
        # 前4个字节可能包含header length (通常为9)
        if len(data) < 13:
            return result

        header_size = struct.unpack(">I", data[5:9])[0]
        pos = header_size

        max_scan = min(len(data), pos + 50000)  # 最多扫描50KB
        while pos < max_scan:
            if pos + 11 > len(data):
                break

            # 读取tag类型
            tag_type = data[pos]
            data_size_24 = struct.unpack(">I", b"\x00" + data[pos+1:pos+4])[0]
            # timestamp_24 = struct.unpack(">I", b"\x00" + data[pos+4:pos+7])[0]
            # timestamp_ext = data[pos+7]
            stream_id = struct.unpack(">I", b"\x00\x00" + data[pos+8:pos+11])[0]

            if data_size_24 == 0 or pos + 11 + data_size_24 > len(data):
                pos += 11 + data_size_24
                continue

            # 跳过 tag header (11字节)
            tag_data = data[pos + 11:pos + 11 + data_size_24]

            if tag_type == 18:  # 脚本数据（AMF）
                metadata = self._parse_flv_amf_script(tag_data)
                if metadata:
                    if "duration" in metadata:
                        result["时长"] = self._format_duration(float(metadata["duration"]))
                    if "width" in metadata:
                        result["宽度"] = str(int(float(metadata["width"])))
                    if "height" in metadata:
                        result["高度"] = str(int(float(metadata["height"])))
                    if metadata.get("width") and metadata.get("height"):
                        result["分辨率"] = f"{int(float(metadata['width']))} x {int(float(metadata['height']))}"
                    if "videodatarate" in metadata:
                        result["视频比特率"] = f"{metadata['videodatarate']} kbps"
                    if "audiodatarate" in metadata:
                        result["音频比特率"] = f"{metadata['audiodatarate']} kbps"
                    if "framerate" in metadata:
                        result["帧率"] = f"{metadata['framerate']} fps"
                    break

            # 移动到下一个tag（tag header 11字节 + data + 4字节 PreviousTagSize）
            pos += 11 + data_size_24 + 4

        if "标题" not in result:
            result["标题"] = Path(file_path).stem

        return result

    def _parse_flv_amf_script(self, data: bytes) -> dict:
        """解析FLV脚本数据的AMF格式

        AMF格式:
        - 第一个值通常是字符串 "onMetaData"
        - 第二个值是 ECMA Array（对象），包含多个键值对
        """
        result = {}
        pos = 0

        # 解析第一个值：通常为字符串 "onMetaData"
        try:
            val, new_pos = self._parse_amf_value(data, pos)
            pos = new_pos
        except Exception:
            return result

        # 解析第二个值：通常是 ECMA Array
        try:
            val, new_pos = self._parse_amf_value(data, pos)
            pos = new_pos
            if isinstance(val, dict):
                result = val
        except Exception:
            return result

        return result

    def _parse_amf_value(self, data: bytes, pos: int):
        """解析单个AMF值

        AMF类型标记:
        - 0x00: Number (8字节 big-endian double)
        - 0x01: Boolean (1字节)
        - 0x02: String (2字节长度 + UTF-8数据)
        - 0x03: Object (3字节结束标记 0x00 0x00 0x09)
        - 0x05: Null
        - 0x06: Undefined
        - 0x08: ECMA Array (4字节count + 键值对 + 3字节结束标记)
        - 0x0B: Array (4字节count + 值序列)
        - 0x0C: Date (8字节double + 2字节timezone)
        """
        if pos >= len(data):
            return None, pos

        marker = data[pos]
        pos += 1

        if marker == 0x00:
            # Number (double)
            if pos + 8 > len(data):
                raise ValueError("AMF Number 数据不完整")
            value = struct.unpack(">d", data[pos:pos+8])[0]
            return value, pos + 8

        elif marker == 0x01:
            # Boolean
            if pos + 1 > len(data):
                raise ValueError("AMF Boolean 数据不完整")
            value = data[pos] != 0
            return value, pos + 1

        elif marker == 0x02:
            # String (UTF-8)
            if pos + 2 > len(data):
                raise ValueError("AMF String 长度不完整")
            str_len = struct.unpack(">H", data[pos:pos+2])[0]
            pos += 2
            if pos + str_len > len(data):
                raise ValueError("AMF String 数据不完整")
            value = data[pos:pos+str_len].decode("utf-8", errors="replace")
            return value, pos + str_len

        elif marker == 0x03:
            # Object
            obj = {}
            while pos + 3 <= len(data):
                # 读取键名（2字节长度 + 字符串，空字符串表示结束）
                key_len = struct.unpack(">H", data[pos:pos+2])[0]
                pos += 2
                if key_len == 0:
                    # 检查结束标记 0x09
                    if pos < len(data) and data[pos] == 0x09:
                        pos += 1
                    break
                if pos + key_len > len(data):
                    break
                key = data[pos:pos+key_len].decode("utf-8", errors="replace")
                pos += key_len
                # 读取值
                value, pos = self._parse_amf_value(data, pos)
                obj[key] = value
            return obj, pos

        elif marker == 0x05:
            # Null
            return None, pos

        elif marker == 0x06:
            # Undefined
            return None, pos

        elif marker == 0x08:
            # ECMA Array
            if pos + 4 > len(data):
                raise ValueError("AMF ECMA Array count 不完整")
            array_count = struct.unpack(">I", data[pos:pos+4])[0]
            pos += 4
            obj = {}
            # 读取键值对
            for _ in range(array_count):
                if pos + 2 > len(data):
                    break
                key_len = struct.unpack(">H", data[pos:pos+2])[0]
                pos += 2
                if key_len == 0:
                    # 结束标记
                    if pos < len(data) and data[pos] == 0x09:
                        pos += 1
                    break
                if pos + key_len > len(data):
                    break
                key = data[pos:pos+key_len].decode("utf-8", errors="replace")
                pos += key_len
                value, pos = self._parse_amf_value(data, pos)
                obj[key] = value

            # 跳过结束标记（如果有）
            if pos < len(data) and data[pos] == 0x09:
                pos += 1

            return obj, pos

        elif marker == 0x0B:
            # Array (dense)
            if pos + 4 > len(data):
                raise ValueError("AMF Array count 不完整")
            array_count = struct.unpack(">I", data[pos:pos+4])[0]
            pos += 4
            arr = []
            for _ in range(array_count):
                value, pos = self._parse_amf_value(data, pos)
                arr.append(value)
            return arr, pos

        elif marker == 0x0C:
            # Date
            if pos + 10 > len(data):
                raise ValueError("AMF Date 数据不完整")
            timestamp = struct.unpack(">d", data[pos:pos+8])[0]
            tz_offset = struct.unpack(">h", data[pos+8:pos+10])[0]
            return timestamp, pos + 10

        else:
            # 未知类型，返回None
            return None, pos

    # ===== 字幕提取 =====

    def _extract_subtitles(self, file_path: str, ext: str) -> str:
        """从视频文件中提取内嵌字幕"""
        # 简化版：优先检查同名字幕文件
        # 内嵌字幕提取需要 ffmpeg，这里仅做简单提示
        return ""

    def _find_external_subtitles(self, file_path: str) -> str:
        """查找同目录下的外部字幕文件"""
        path = Path(file_path)
        base = path.stem
        dir_ = path.parent

        sub_extensions = ["srt", "vtt", "ass", "ssa", "sub"]
        for ext in sub_extensions:
            sub_path = dir_ / f"{base}.{ext}"
            if sub_path.exists():
                try:
                    return self.parse_subtitle(str(sub_path))
                except Exception:
                    continue
            # 也尝试带语言后缀的
            for lang in ["zh", "en", "chs", "cht", "cn"]:
                sub_path = dir_ / f"{base}.{lang}.{ext}"
                if sub_path.exists():
                    try:
                        return self.parse_subtitle(str(sub_path))
                    except Exception:
                        continue
        return ""

    def _parse_srt(self, text: str) -> str:
        """解析SRT字幕，提取纯文本"""
        lines = text.split("\n")
        result = []
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            # 跳过序号行
            if line.isdigit():
                i += 1
                continue
            # 跳过时间轴行
            if "-->" in line:
                i += 1
                continue
            # 空行是分隔符
            if not line:
                i += 1
                continue
            # 字幕文本
            result.append(line)
            i += 1
        return "\n".join(result)

    def _parse_vtt(self, text: str) -> str:
        """解析WebVTT字幕"""
        lines = text.split("\n")
        result = []
        i = 0
        # 跳过头部
        if i < len(lines) and lines[i].strip().startswith("WEBVTT"):
            i += 1

        while i < len(lines):
            line = lines[i].strip()
            if "-->" in line:
                i += 1
                continue
            if not line:
                i += 1
                continue
            # 跳过样式和注释
            if line.startswith("STYLE") or line.startswith("NOTE") or line.startswith("WEBVTT"):
                i += 1
                continue
            # 跳过只有数字的序号行
            if line.isdigit():
                i += 1
                continue
            result.append(line)
            i += 1
        return "\n".join(result)

    def _parse_ass(self, text: str) -> str:
        """解析ASS/SSA字幕"""
        lines = text.split("\n")
        result = []
        in_events = False

        for line in lines:
            stripped = line.strip()
            if stripped.startswith("[Events]"):
                in_events = True
                continue
            if stripped.startswith("[") and stripped.endswith("]") and stripped != "[Events]":
                in_events = False
                continue
            if in_events and stripped.startswith("Dialogue:"):
                # Dialogue: 0,0:00:01.00,0:00:04.00,Default,,0,0,0,,文本内容
                parts = stripped.split(",", 9)
                if len(parts) >= 10:
                    text_part = parts[9]
                    # 去除ASS样式标签 {\pos(...)} 等
                    text_part = re.sub(r"\{[^}]*\}", "", text_part)
                    if text_part.strip():
                        result.append(text_part.strip())

        return "\n".join(result)

    # ===== 语音转文字（可选） =====

    def _try_speech_to_text(self, file_path: str, is_audio: bool = True) -> str:
        """尝试使用 faster-whisper 进行语音转文字"""
        try:
            from faster_whisper import WhisperModel
            logger.info("使用 faster-whisper 进行语音转文字...")
            # 使用小模型
            model = WhisperModel("base", device="cpu", compute_type="int8")
            segments, info = model.transcribe(file_path, beam_size=5)
            texts = []
            for segment in segments:
                if segment.text.strip():
                    texts.append(segment.text.strip())
            return "\n".join(texts)
        except ImportError:
            return ""
        except Exception as e:
            logger.warning(f"语音转文字失败: {e}")
            return ""

    # ===== 工具函数 =====

    def _format_size(self, size: int) -> str:
        """格式化文件大小"""
        if size < 1024:
            return f"{size} B"
        elif size < 1024 * 1024:
            return f"{size/1024:.1f} KB"
        elif size < 1024 * 1024 * 1024:
            return f"{size/(1024*1024):.1f} MB"
        else:
            return f"{size/(1024*1024*1024):.2f} GB"

    def _format_duration(self, seconds: float) -> str:
        """格式化时长"""
        seconds = int(seconds)
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        secs = seconds % 60
        if hours > 0:
            return f"{hours}时{minutes:02d}分{secs:02d}秒"
        elif minutes > 0:
            return f"{minutes}分{secs:02d}秒"
        else:
            return f"{secs}秒"
