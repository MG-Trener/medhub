export function signNonce(nonce) {
  return new Promise((resolve, reject) => {
    const socket = new WebSocket('wss://127.0.0.1:13579/')
    let settled = false
    const finish = (error, result) => {
      if (settled) return
      settled = true
      clearTimeout(timer)
      socket.close()
      error ? reject(error) : resolve(result)
    }
    const timer = setTimeout(() => finish(new Error('Время подписания истекло')), 120000)
    socket.onerror = () => finish(new Error('Запустите NCALayer и разрешите соединение с ним'))
    socket.onclose = () => finish(new Error('Соединение с NCALayer закрыто'))
    socket.onopen = () => socket.send(JSON.stringify({ module: 'kz.gov.pki.knca.basics', method: 'sign', args: {
      format: 'cms', data: nonce, signingParams: { decode: true, encapsulate: true, digested: false },
      signerParams: { extKeyUsageOids: ['1.2.398.3.3.4.1.1'] }, locale: 'ru'
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
