import { ref, onBeforeUnmount } from 'vue'

export function useRecorder() {
  const devices = ref([]), selected = ref(localStorage.getItem('medhub.microphone') || '')
  const recording = ref(false), paused = ref(false), recorderError = ref(''), seconds = ref(0), audioUrl = ref(''), audioBlob = ref(null), level = ref(0)
  let stream, recorder, chunks = [], timer, audioContext, animation, stopPromise, resolveStop, disposed = false
  const release = () => {
    clearInterval(timer); cancelAnimationFrame(animation)
    stream?.getTracks().forEach(t => t.stop())
    audioContext?.close(); audioContext = null
    level.value = 0
  }
  async function requestMicrophone(audio) {
    let expired = false, timeout
    const request = navigator.mediaDevices.getUserMedia({ audio }).then(value => {
      if (expired) { value.getTracks().forEach(t => t.stop()); throw new Error('Запрос микрофона отменён') }
      return value
    })
    try {
      return await Promise.race([request, new Promise((_, reject) => {
        timeout = setTimeout(() => { expired = true; reject(new Error('Разрешите микрофон в браузере и повторите. Можно загрузить готовую запись.')) }, 15000)
      })])
    } catch (error) {
      const messages = {NotAllowedError:'Браузер запретил микрофон. Разрешите доступ в настройках сайта.', NotFoundError:'Микрофон не найден. Подключите устройство или загрузите запись.', NotReadableError:'Микрофон занят или недоступен. Проверьте другое приложение.', OverconstrainedError:'Сохранённый микрофон недоступен. Обновите список устройств.'}
      throw new Error(messages[error.name] || error.message)
    } finally { clearTimeout(timeout) }
  }
  async function discover() {
    if (!navigator.mediaDevices?.getUserMedia) throw new Error('Микрофон доступен через HTTPS или localhost')
    const permission = await requestMicrophone(true)
    permission.getTracks().forEach(t => t.stop())
    devices.value = (await navigator.mediaDevices.enumerateDevices()).filter(x => x.kind === 'audioinput')
    if (selected.value && !devices.value.some(d => d.deviceId === selected.value)) selected.value = ''
  }
  function saveDevice() { localStorage.setItem('medhub.microphone', selected.value) }
  function clearAudio() {
    if (audioUrl.value) URL.revokeObjectURL(audioUrl.value)
    audioUrl.value = ''; audioBlob.value = null; seconds.value = 0
  }
  function setAudio(blob) {
    clearAudio(); audioBlob.value = blob; audioUrl.value = URL.createObjectURL(blob)
  }
  function pause() {
    if (recorder?.state === 'recording') { recorder.pause(); paused.value = true }
    else if (recorder?.state === 'paused') { recorder.resume(); paused.value = false }
  }
  async function start() {
    if (recording.value) return
    if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) throw new Error('Браузер не поддерживает запись. Откройте сайт в современном браузере через HTTPS.')
    stream = await requestMicrophone({ deviceId: selected.value ? { exact: selected.value } : undefined, echoCancellation: true, noiseSuppression: true })
    try {
      clearAudio(); chunks = []; recorderError.value = ''; paused.value = false
      stopPromise = new Promise(resolve => { resolveStop = resolve })
      const mimeType = ['audio/webm;codecs=opus', 'audio/mp4', 'audio/ogg;codecs=opus'].find(t => MediaRecorder.isTypeSupported(t))
      recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined)
      recorder.ondataavailable = e => { if (e.data.size) chunks.push(e.data) }
      recorder.onstop = () => {
        if (disposed) { recording.value = false; release(); resolveStop?.(null); return }
        audioBlob.value = new Blob(chunks, { type: recorder.mimeType || 'audio/webm' })
        audioUrl.value = URL.createObjectURL(audioBlob.value)
        recording.value = false; paused.value = false; release(); resolveStop?.(audioBlob.value)
      }
      recorder.onerror = () => { recorderError.value = 'Запись прервалась. Проверьте сохранённый фрагмент.'; if (recorder.state !== 'inactive') recorder.stop(); else { recording.value = false; release(); resolveStop?.(audioBlob.value) } }
      stream.getAudioTracks().forEach(track => { track.onended = () => { recorderError.value = 'Микрофон отключён. Сохранён записанный фрагмент.'; stop() } })
      recorder.start(1000); recording.value = true
      timer = setInterval(() => { if (paused.value) return; seconds.value++; if (seconds.value >= 3600) stop() }, 1000)
      audioContext = new AudioContext()
      const analyser = audioContext.createAnalyser(); analyser.fftSize = 256
      audioContext.createMediaStreamSource(stream).connect(analyser)
      const data = new Uint8Array(analyser.frequencyBinCount)
      const tick = () => { analyser.getByteFrequencyData(data); level.value = data.reduce((a, b) => a + b, 0) / data.length / 128; animation = requestAnimationFrame(tick) }
      tick(); saveDevice()
    } catch (error) { release(); throw error }
  }
  async function stop() {
    if (recorder && recorder.state !== 'inactive') { recorder.stop(); return stopPromise }
    return audioBlob.value
  }
  const beforeUnload = event => { if (recording.value || audioBlob.value) { event.preventDefault(); event.returnValue = '' } }
  window.addEventListener('beforeunload', beforeUnload)
  onBeforeUnmount(() => { disposed = true; stop(); release(); clearAudio(); window.removeEventListener('beforeunload', beforeUnload) })
  return { devices, selected, recording, paused, recorderError, seconds, audioUrl, audioBlob, level, discover, saveDevice, start, stop, pause, setAudio, clearAudio }
}
