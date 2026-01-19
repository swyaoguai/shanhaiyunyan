"""
配置验证模块
提供配置参数的验证和校验功能
"""

import re
from typing import Optional, List, Dict, Any, Union
from dataclasses import dataclass
from urllib.parse import urlparse

from ..constants import LLM_DEFAULTS, VALIDATION_RULES


@dataclass
class ValidationError:
    """验证错误"""
    field: str
    message: str
    value: Any = None
    
    def __str__(self) -> str:
        if self.value is not None:
            return f"{self.field}: {self.message} (got: {self.value})"
        return f"{self.field}: {self.message}"


@dataclass
class ValidationResult:
    """验证结果"""
    is_valid: bool
    errors: List[ValidationError]
    warnings: List[str]
    
    @property
    def error_messages(self) -> List[str]:
        return [str(e) for e in self.errors]
    
    def raise_if_invalid(self):
        """如果验证失败则抛出异常"""
        if not self.is_valid:
            raise ValueError(f"Configuration validation failed: {'; '.join(self.error_messages)}")


class ConfigValidator:
    """配置验证器"""
    
    def __init__(self):
        self.errors: List[ValidationError] = []
        self.warnings: List[str] = []
    
    def reset(self):
        """重置验证状态"""
        self.errors = []
        self.warnings = []
    
    def validate_url(
        self, 
        field: str, 
        value: str, 
        required: bool = True,
        allowed_schemes: List[str] = None
    ) -> bool:
        """
        验证URL格式
        
        Args:
            field: 字段名
            value: URL值
            required: 是否必填
            allowed_schemes: 允许的协议列表
        """
        if not value:
            if required:
                self.errors.append(ValidationError(field, "URL is required"))
                return False
            return True
        
        try:
            result = urlparse(value)
            
            if not result.scheme:
                self.errors.append(ValidationError(field, "URL must include scheme (http/https)", value))
                return False
            
            if allowed_schemes and result.scheme not in allowed_schemes:
                self.errors.append(ValidationError(
                    field, 
                    f"URL scheme must be one of: {allowed_schemes}", 
                    value
                ))
                return False
            
            if not result.netloc:
                self.errors.append(ValidationError(field, "Invalid URL format", value))
                return False
            
            return True
            
        except Exception as e:
            self.errors.append(ValidationError(field, f"Invalid URL: {str(e)}", value))
            return False
    
    def validate_api_base(self, field: str, value: str, required: bool = True) -> bool:
        """验证API基础URL"""
        if not self.validate_url(field, value, required, ["http", "https"]):
            return False
        
        # 检查是否以/v1结尾（OpenAI兼容格式）
        if value and not value.rstrip('/').endswith('/v1'):
            self.warnings.append(f"{field}: URL should typically end with '/v1' for OpenAI-compatible APIs")
        
        return True
    
    def validate_api_key(self, field: str, value: str, required: bool = True) -> bool:
        """验证API密钥"""
        if not value:
            if required:
                self.errors.append(ValidationError(field, "API key is required"))
                return False
            return True
        
        # 基本长度检查
        if len(value) < 10:
            self.warnings.append(f"{field}: API key seems too short")
        
        # 检查常见的占位符
        placeholder_patterns = [
            r'^your[-_]?api[-_]?key',
            r'^sk-xxx+',
            r'^api[-_]?key[-_]?here',
            r'^<.*>$',
            r'^\*+$'
        ]
        for pattern in placeholder_patterns:
            if re.match(pattern, value, re.IGNORECASE):
                self.errors.append(ValidationError(field, "API key appears to be a placeholder", "***"))
                return False
        
        return True
    
    def validate_model_name(self, field: str, value: str, required: bool = True) -> bool:
        """验证模型名称"""
        if not value:
            if required:
                self.errors.append(ValidationError(field, "Model name is required"))
                return False
            return True
        
        # 模型名称格式检查
        if len(value) < 2:
            self.errors.append(ValidationError(field, "Model name is too short", value))
            return False
        
        if len(value) > 100:
            self.errors.append(ValidationError(field, "Model name is too long", value[:20] + "..."))
            return False
        
        return True
    
    def validate_temperature(self, field: str, value: float) -> bool:
        """验证温度参数"""
        if value < 0 or value > 2:
            self.errors.append(ValidationError(
                field, 
                "Temperature must be between 0 and 2", 
                value
            ))
            return False
        
        if value > 1.5:
            self.warnings.append(f"{field}: Temperature above 1.5 may produce less coherent output")
        
        return True
    
    def validate_max_tokens(self, field: str, value: int) -> bool:
        """验证最大Token数"""
        if value < 1:
            self.errors.append(ValidationError(field, "Max tokens must be positive", value))
            return False
        
        if value > 200000:
            self.errors.append(ValidationError(
                field, 
                "Max tokens exceeds typical model limits (200000)", 
                value
            ))
            return False
        
        if value < 100:
            self.warnings.append(f"{field}: Max tokens below 100 may limit output quality")
        
        return True
    
    def validate_positive_int(
        self, 
        field: str, 
        value: int, 
        min_val: int = 1, 
        max_val: Optional[int] = None
    ) -> bool:
        """验证正整数"""
        if value < min_val:
            self.errors.append(ValidationError(
                field, 
                f"Value must be at least {min_val}", 
                value
            ))
            return False
        
        if max_val is not None and value > max_val:
            self.errors.append(ValidationError(
                field, 
                f"Value must not exceed {max_val}", 
                value
            ))
            return False
        
        return True
    
    def validate_string_length(
        self, 
        field: str, 
        value: str, 
        min_len: int = VALIDATION_RULES.MIN_STRING_LENGTH,
        max_len: int = VALIDATION_RULES.MAX_STRING_LENGTH
    ) -> bool:
        """验证字符串长度"""
        if len(value) < min_len:
            self.errors.append(ValidationError(
                field, 
                f"String must be at least {min_len} characters", 
                len(value)
            ))
            return False
        
        if len(value) > max_len:
            self.errors.append(ValidationError(
                field, 
                f"String exceeds maximum length of {max_len}", 
                len(value)
            ))
            return False
        
        return True
    
    def get_result(self) -> ValidationResult:
        """获取验证结果"""
        return ValidationResult(
            is_valid=len(self.errors) == 0,
            errors=self.errors.copy(),
            warnings=self.warnings.copy()
        )


def validate_global_api_config(
    api_base: str,
    api_key: str,
    model: str,
    temperature: float = LLM_DEFAULTS.TEMPERATURE,
    max_tokens: int = LLM_DEFAULTS.MAX_TOKENS
) -> ValidationResult:
    """
    验证全局API配置
    
    Returns:
        验证结果
    """
    validator = ConfigValidator()
    
    validator.validate_api_base("api_base", api_base)
    validator.validate_api_key("api_key", api_key)
    validator.validate_model_name("model", model)
    validator.validate_temperature("temperature", temperature)
    validator.validate_max_tokens("max_tokens", max_tokens)
    
    return validator.get_result()


def validate_agent_config(
    agent_name: str,
    api_base: str = "",
    api_key: str = "",
    model: str = "",
    temperature: float = LLM_DEFAULTS.TEMPERATURE,
    max_tokens: int = LLM_DEFAULTS.MAX_TOKENS,
    use_global: bool = True
) -> ValidationResult:
    """
    验证Agent配置
    
    如果use_global=True，则API相关字段不是必填
    """
    validator = ConfigValidator()
    
    # Agent名称验证
    if not agent_name:
        validator.errors.append(ValidationError("agent_name", "Agent name is required"))
    
    # 如果不使用全局配置，则需要验证API配置
    if not use_global:
        validator.validate_api_base("api_base", api_base, required=True)
        validator.validate_api_key("api_key", api_key, required=True)
        validator.validate_model_name("model", model, required=True)
    else:
        # 即使使用全局配置，如果提供了值也要验证格式
        if api_base:
            validator.validate_api_base("api_base", api_base, required=False)
        if api_key:
            validator.validate_api_key("api_key", api_key, required=False)
        if model:
            validator.validate_model_name("model", model, required=False)
    
    validator.validate_temperature("temperature", temperature)
    validator.validate_max_tokens("max_tokens", max_tokens)
    
    return validator.get_result()


def validate_novel_params(
    novel_type: str,
    volume_count: int = 1,
    chapters_per_volume: int = 10
) -> ValidationResult:
    """验证小说创作参数"""
    validator = ConfigValidator()
    
    if not novel_type:
        validator.errors.append(ValidationError("novel_type", "Novel type is required"))
    
    validator.validate_positive_int("volume_count", volume_count, min_val=1, max_val=100)
    validator.validate_positive_int("chapters_per_volume", chapters_per_volume, min_val=1, max_val=100)
    
    total_chapters = volume_count * chapters_per_volume
    if total_chapters > 500:
        validator.warnings.append(f"Total chapters ({total_chapters}) is very high, may take a long time")
    
    return validator.get_result()


# 模块职责说明：提供配置参数验证功能，包括URL、API密钥、模型名称和小说创作参数的校验。