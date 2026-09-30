import { ref, onBeforeUnmount } from 'vue'

export function useRecorder() {
  const devices = ref([]), selected = ref(localStorage.getItem('medhub.microphone') || '')
  const recording = ref(false), seconds = ref(0), audioUrl = ref(''), audioBlob = ref(null), level = ref(0)
  let stream, recorder, chunks = [], timer, audioContext, animation
  const release = () => {
    clearInterval(timer); cancelAnimationFrame(animation)
    stream?.getTracks().forEach(t => t.stop())
    audioContext?.close(); audioContext = null
    level.value = 0
  }
  async function discover() {
    if (!navigator.mediaDevices?.getUserMedia) throw new Error('Микрофон доступен через HTTPS или localhost')
    const permission = await navigator.mediaDevices.getUserMedia({ audio: true })
    permission.getTracks().forEach(t => t.stop())
    devices.value = (await navigator.mediaDevices.enumerateDevices()).filter(x => x.kind === 'audioinput')
    if (selected.value && !devices.value.some(d => d.deviceId === selected.value)) selected.value = ''
  }
  function saveDevice() { localStorage.setItem('medhub.microphone', selected.value) }
  function clearAudio() {
    if (audioUrl.value) URL.revokeObjectURL(audioUrl.value)
    audioUrl.value = ''; audioBlob.value = null; seconds.value = 0
  }
  async function start() {
    if (recording.value) return
    if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) throw new Error('Браузер не поддерживает запись. Откройте сайт в современном браузере через HTTPS.')
    stream = await navigator.mediaDevices.getUserMedia({ audio: { deviceId: selected.value ? { exact: selected.value } : undefined, echoCancellation: true, noiseSuppression: true } })
    try {
      clearAudio(); chunks = []
      const mimeType = ['audio/webm;codecs=opus', 'audio/mp4', 'audio/ogg;codecs=opus'].find(t => MediaRecorder.isTypeSupported(t))
      recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined)
      recorder.ondataavailable = e => { if (e.data.size) chunks.push(e.data) }
      recorder.onstop = () => {
        audioBlob.value = new Blob(chunks, { type: recorder.mimeType || 'audio/webm' })
        audioUrl.value = URL.createObjectURL(audioBlob.value)
        recording.value = false; release()
      }
      recorder.onerror = () => { recording.value = false; release() }
      recorder.start(1000); recording.value = true
      timer = setInterval(() => { seconds.value++; if (seconds.value >= 3600) stop() }, 1000)
      audioContext = new AudioContext()
      const analyser = audioContext.createAnalyser(); analyser.fftSize = 256
      audioContext.createMediaStreamSource(stream).connect(analyser)
      const data = new Uint8Array(analyser.frequencyBinCount)
      const tick = () => { analyser.getByteFrequencyData(data); level.value = data.reduce((a, b) => a + b, 0) / data.length / 128; animation = requestAnimationFrame(tick) }
      tick(); saveDevice()
    } catch (error) { release(); throw error }
  }
  function stop() { if (recorder?.state === 'recording') recorder.stop() }
  const beforeUnload = event => { if (recording.value || audioBlob.value) { event.preventDefault(); event.returnValue = '' } }
  window.addEventListener('beforeunload', beforeUnload)
  onBeforeUnmount(() => { stop(); release(); clearAudio(); window.removeEventListener('beforeunload', beforeUnload) })
  return { devices, selected, recording, seconds, audioUrl, audioBlob, level, discover, saveDevice, start, stop, clearAudio }
}
