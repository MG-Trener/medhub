function signCms(data, { signal, document = false, xml = false } = {}) {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) { reject(new Error('Подписание отменено')); return }
    const socket = new WebSocket('wss://127.0.0.1:13579/')
    let settled = false
    const finish = (error, result) => {
      if (settled) return
      settled = true
      clearTimeout(timer)
      signal?.removeEventListener('abort', cancel)
      socket.close()
      error ? reject(error) : resolve(result)
    }
    const cancel = () => finish(new Error('Подписание отменено'))
    const timer = setTimeout(() => finish(new Error('Время подписания истекло')), 120000)
    signal?.addEventListener('abort', cancel, { once: true })
    socket.onerror = () => finish(new Error('Запустите NCALayer и разрешите соединение с ним'))
    socket.onclose = () => finish(new Error('Соединение с NCALayer закрыто'))
    socket.onopen = () => socket.send(JSON.stringify({ module: 'kz.gov.pki.knca.basics', method: 'sign', args: {
      format: xml ? 'xml' : 'cms', data, signingParams: xml ? {} : { decode: true, encapsulate: true, digested: false, ...(document ? { tsaProfile: {} } : {}) },
      signerParams: { extKeyUsageOids: document ? ['1.3.6.1.5.5.7.3.4', '1.2.398.3.3.4.1.1'] : ['1.2.398.3.3.4.1.1'] }, locale: 'ru'
    } }))
    socket.onmessage = ({ data }) => {
      try {
        const response = JSON.parse(data)
        if (response.result?.version) return
        if (!response.status) return finish(new Error('Подписание отменено или ключ недоступен'))
        const result = response.body?.result
        const signatures = result?.signatures ?? result
        const signature = Array.isArray(signatures) ? signatures[0] : signatures
        if (typeof signature !== 'string') throw new Error()
        finish(null, signature)
      } catch { finish(new Error('Некорректный ответ NCALayer')) }
    }
  })
}

// Вход подписывает XML; согласие — CMS с точными байтами PDF.
export const signData = (data, options = {}) => signCms(data, { ...options, document: true })
export const signNonce = nonce => signCms(nonce)
export const signXml = (data, options = {}) => signCms(data, { ...options, xml: true })
