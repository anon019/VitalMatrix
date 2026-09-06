/**
 * 应用配置
 */

// API基础地址
// 根据环境自动切换（开发环境使用本地，生产环境使用域名）
const getApiBaseUrl = () => {
  // 获取当前账号信息
  const accountInfo = wx.getAccountInfoSync()
  const envVersion = accountInfo.miniProgram.envVersion

  if (envVersion === 'develop') {
    // 开发版：使用远程服务器（本地调试时也可改为 http://localhost:8000）
    return 'https://your-domain.example.com'
  } else if (envVersion === 'trial') {
    // 体验版：使用测试服务器
    return 'https://your-domain.example.com'
  } else {
    // 正式版：使用生产服务器
    return 'https://your-domain.example.com'
  }
}

module.exports = {
  // API基础地址
  API_BASE_URL: getApiBaseUrl(),

  // API超时时间（毫秒）
  REQUEST_TIMEOUT: 10000,

  // Token存储key
  TOKEN_KEY: 'token',
  USER_INFO_KEY: 'userInfo',
  USER_ID_KEY: 'user_id',
  AUTH_MODE_KEY: 'auth_mode',
  LEGACY_AUTH_MODE_KEY: 'authMode',
  AUTH_SESSION_KEY: 'authSessionV2',
  AUTH_STORAGE_VERSION_KEY: 'authStorageVersion',
  AUTH_STORAGE_VERSION: 2,
  AUTH_MODE: 'fixed_miniprogram',
  AUTH_EXPIRY_SKEW_MS: 30 * 1000,

  // 应用信息
  APP_NAME: 'Health Assistant',
  APP_VERSION: '0.3.15'
}
