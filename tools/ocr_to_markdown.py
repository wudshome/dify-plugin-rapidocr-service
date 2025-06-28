from collections.abc import Generator
from typing import Any
from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
import requests
import os
import base64
from io import BytesIO
from PIL import Image
from urllib.parse import urlparse
import logging
from dify_plugin.config.logger_format import plugin_logger_handler
import json
# 使用自定义处理器设置日志
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
logger.addHandler(plugin_logger_handler)

class OCRToMarkdownTool(Tool):
    def _convert_rgba_if_needed(self, file_content: BytesIO, filename: str) -> tuple[BytesIO, str]:
        """仅在图片是RGBA模式时转换为RGB JPEG"""
        file_content.seek(0)
        try:
            img = Image.open(file_content)
            if img.mode == 'RGBA':
                img = img.convert('RGB')
                converted = BytesIO()
                img.save(converted, format='JPEG', quality=100)
                converted.seek(0)
                return converted, os.path.splitext(filename)[0] + '.jpg'
            file_content.seek(0)  # 确保指针重置
            return file_content, filename
        except Exception as e:
            raise ValueError(f"RGBA图片转换失败: {str(e)}")

    def _invoke(self, tool_parameters: dict) -> Generator[ToolInvokeMessage]:
        
        uploaded_file = tool_parameters.get('file')
        if not uploaded_file:
            yield self.create_text_message("请上传文件")
            return

        service_url = tool_parameters.get('service_url')
        if not service_url:
            yield self.create_text_message("请设置正确OCR请求路径")
            return
        
        logger.info("OCR Service URL: %s", service_url)

        try:
            # 1. 下载文件
            response = requests.get(uploaded_file.url)
            if response.status_code != 200:
                yield self.create_text_message(f"文件下载失败，状态码: {response.status_code}")
                return
            # logger.info("response.content:",response.content)
            file_content = BytesIO(response.content)
            filename = uploaded_file.filename
            
            # 2. 检查是否为图片
            try:
                img = Image.open(file_content)
                img.verify()  # 验证图片格式
                file_content.seek(0)  # 重置指针以便后续处理
                try:
                    file_content, filename = self._convert_rgba_if_needed(file_content, filename)
                except ValueError as e:
                    yield self.create_text_message(str(e))
                    return
            except Exception as e:
                yield self.create_text_message(f"文件不是有效的图片: {str(e)}")
                return
            logger.info(f"filename: {filename}") 
            # logger.debug(f"file_content: {file_content}")
            # 3. 发送到OCR服务
            files = {'image_file': (filename, file_content)}
            data = { 'use_det': 'true',
                     'use_cls': 'true',
                     'use_rec': 'true',
                     'word_box': 'true'}
            headers ={'Content-Type': 'multipart/form-data', 'accept': 'application/json'}
            ocr_response = requests.post(
                service_url,
                files=files,
                data=data
            )

            if ocr_response.status_code != 200:
                yield self.create_text_message(f"OCR处理失败，状态码: {ocr_response}")  
                #yield self.create_text_message(f"OCR处理失败，状态码: {ocr_response.status_code}")
                return
            # logger.info(f"OCR处理成功，结果: {ocr_response.json()}")
            result = ocr_response.json().get("result").get("txts")
            # 将结果以json格式返回
            yield self.create_text_message(text=json.dumps(result, ensure_ascii=False))
            #yield self.create_json_message(result)
            
             
        except requests.exceptions.RequestException as e:
            yield self.create_text_message(f"网络请求失败: {str(e)}")
        except Exception as e:
            yield self.create_text_message(f"处理失败: {str(e)}")