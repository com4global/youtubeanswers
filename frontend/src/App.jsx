import { useEffect, useMemo, useRef, useState } from 'react'
import './App.css'

const API_BASE =
  import.meta.env.VITE_API_BASE ||
  (window.location.hostname === 'localhost'
    ? 'http://localhost:8000'
    : '/api')

function App() {
  const [activeMenu, setActiveMenu] = useState('course')
  const [playlistUrl, setPlaylistUrl] = useState('')
  const [jobId, setJobId] = useState('')
  const [course, setCourse] = useState(null)
  const [status, setStatus] = useState(null)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [error, setError] = useState('')
  const [battlecardChannels, setBattlecardChannels] = useState([''])
  const [maxVideosPerChannel, setMaxVideosPerChannel] = useState(4)
  const [battlecardData, setBattlecardData] = useState(null)
  const [battlecardError, setBattlecardError] = useState('')
  const [isBattlecardLoading, setIsBattlecardLoading] = useState(false)
  const [aiProductsData, setAiProductsData] = useState(null)
  const [aiProductsError, setAiProductsError] = useState('')
  const [isAiProductsLoading, setIsAiProductsLoading] = useState(false)
  const [aiSearch, setAiSearch] = useState('')
  const [aiPage, setAiPage] = useState(1)
  const AI_PAGE_SIZE = 24
  const aiSearchTimer = useRef(null)
  const aiAbortRef = useRef(null)

  const isCourseReady = status?.status === 'completed' && status?.result
  const showLogs = import.meta.env.VITE_SHOW_LOGS === 'true'

  const courseData = useMemo(() => course || status?.result || null, [course, status])
  const battlecardEvidence = useMemo(() => {
    const evidence = battlecardData?.evidence || []
    const byVideo = new Map()
    evidence.forEach((item) => {
      if (!item?.video_url) return
      if (!byVideo.has(item.video_url)) {
        byVideo.set(item.video_url, { snippets: [], channelUrl: item.channel_url || '' })
      }
      if (item.text) {
        byVideo.get(item.video_url).snippets.push(item.text)
      }
      if (item.channel_url && !byVideo.get(item.video_url).channelUrl) {
        byVideo.get(item.video_url).channelUrl = item.channel_url
      }
    })
    return byVideo
  }, [battlecardData])

  useEffect(() => {
    if (activeMenu !== 'ai-market') {
      return
    }
    if (aiSearchTimer.current) {
      clearTimeout(aiSearchTimer.current)
    }
    if (aiAbortRef.current) {
      aiAbortRef.current.abort()
    }
    aiSearchTimer.current = setTimeout(async () => {
      const controller = new AbortController()
      aiAbortRef.current = controller
      setAiProductsError('')
      setIsAiProductsLoading(true)
      try {
        const response = await fetch(
          `${API_BASE}/ai-products?offset=0&limit=${AI_PAGE_SIZE}&q=${encodeURIComponent(aiSearch)}`,
          { signal: controller.signal }
        )
        if (!response.ok) {
          throw new Error('Unable to load AI product directory')
        }
        const data = await response.json()
        setAiProductsData(data)
        setAiPage(1)
      } catch (err) {
        if (err.name !== 'AbortError') {
          setAiProductsError(err.message || 'Failed to load AI products')
        }
      } finally {
        setIsAiProductsLoading(false)
      }
    }, 400)
    return () => {
      if (aiSearchTimer.current) {
        clearTimeout(aiSearchTimer.current)
      }
      if (aiAbortRef.current) {
        aiAbortRef.current.abort()
      }
    }
  }, [API_BASE, activeMenu, aiSearch])

  const handleSyncAiProducts = async () => {
    setAiProductsError('')
    setIsAiProductsLoading(true)
    try {
      const response = await fetch(`${API_BASE}/ai-products/sync?offset=0&limit=${AI_PAGE_SIZE}`, { method: 'POST' })
      if (!response.ok) {
        throw new Error('Unable to sync AI products')
      }
      const data = await response.json()
      setAiProductsData(data)
      setAiPage(1)
    } catch (err) {
      setAiProductsError(err.message || 'Failed to sync AI products')
    } finally {
      setIsAiProductsLoading(false)
    }
  }

  const handleSyncZapierList = async () => {
    setAiProductsError('')
    setIsAiProductsLoading(true)
    try {
      const response = await fetch(`${API_BASE}/ai-products/sync-zapier?offset=0&limit=${AI_PAGE_SIZE}`, { method: 'POST' })
      if (!response.ok) {
        throw new Error('Unable to sync Zapier list')
      }
      const data = await response.json()
      setAiProductsData(data)
      setAiPage(1)
    } catch (err) {
      setAiProductsError(err.message || 'Failed to sync Zapier list')
    } finally {
      setIsAiProductsLoading(false)
    }
  }

  const handleSyncSources = async () => {
    setAiProductsError('')
    setIsAiProductsLoading(true)
    try {
      const response = await fetch(`${API_BASE}/ai-products/sync-sources?offset=0&limit=${AI_PAGE_SIZE}`, { method: 'POST' })
      if (!response.ok) {
        throw new Error('Unable to sync sources')
      }
      const data = await response.json()
      setAiProductsData(data)
      setAiPage(1)
    } catch (err) {
      setAiProductsError(err.message || 'Failed to sync sources')
    } finally {
      setIsAiProductsLoading(false)
    }
  }

  useEffect(() => {
    if (!jobId || !status || status.status === 'completed' || status.status === 'failed') {
      return
    }

    const timer = setTimeout(async () => {
      try {
        const response = await fetch(`${API_BASE}/course/${jobId}`)
        if (!response.ok) {
          throw new Error('Failed to fetch course status')
        }
        const data = await response.json()
        setStatus(data)
        if (data.status === 'completed') {
          setCourse(data.result)
        }
      } catch (err) {
        setError(err.message || 'Unable to update status')
      }
    }, 2500)

    return () => clearTimeout(timer)
  }, [API_BASE, jobId, status])

  const handleCreateCourse = async (event) => {
    event.preventDefault()
    setError('')
    setStatus(null)
    setCourse(null)
    if (!playlistUrl.trim()) {
      setError('Please paste a playlist URL.')
      return
    }

    setIsSubmitting(true)
    try {
      const response = await fetch(
        `${API_BASE}/course?playlist_url=${encodeURIComponent(playlistUrl.trim())}`,
        { method: 'POST' }
      )
      if (!response.ok) {
        throw new Error('Unable to start course generation')
      }
      const data = await response.json()
      setJobId(data.job_id)
      setStatus({ status: 'queued', progress: 0, message: 'Queued', job_id: data.job_id })
    } catch (err) {
      setError(err.message || 'Something went wrong')
    } finally {
      setIsSubmitting(false)
    }
  }

  const handleLoadCourse = async () => {
    setError('')
    if (!jobId.trim()) {
      setError('Please enter a job id.')
      return
    }
    setIsSubmitting(true)
    try {
      const response = await fetch(`${API_BASE}/course/${jobId.trim()}`)
      if (!response.ok) {
        throw new Error('Course not found')
      }
      const data = await response.json()
      setStatus(data)
      if (data.result) {
        setCourse(data.result)
      }
    } catch (err) {
      setError(err.message || 'Unable to load course')
    } finally {
      setIsSubmitting(false)
    }
  }

  const handleDownload = async (format) => {
    if (!jobId) return
    setError('')
    try {
      const response = await fetch(`${API_BASE}/course/${jobId}/export/${format}`)
      if (!response.ok) {
        throw new Error(`Unable to download ${format.toUpperCase()}`)
      }
      const blob = await response.blob()
      const contentDisposition = response.headers.get('Content-Disposition') || ''
      const match = contentDisposition.match(/filename="(.+)"/)
      const filename = match ? match[1] : `course.${format}`
      const url = window.URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = filename
      document.body.appendChild(link)
      link.click()
      link.remove()
      window.URL.revokeObjectURL(url)
    } catch (err) {
      setError(err.message || 'Download failed')
    }
  }

  const getEvidenceSnippet = (videoUrl) => {
    if (!videoUrl) return ''
    const entry = battlecardEvidence.get(videoUrl)
    if (!entry?.snippets?.length) return ''
    return entry.snippets[0]
  }

  const getEvidenceChannel = (videoUrl) => {
    if (!videoUrl) return ''
    return battlecardEvidence.get(videoUrl)?.channelUrl || ''
  }

  const updateBattlecardChannel = (index, value) => {
    setBattlecardChannels((prev) => {
      const next = [...prev]
      next[index] = value
      return next
    })
  }

  const addBattlecardChannel = () => {
    setBattlecardChannels((prev) => (prev.length < 4 ? [...prev, ''] : prev))
  }

  const removeBattlecardChannel = (index) => {
    setBattlecardChannels((prev) => prev.filter((_, i) => i !== index))
  }

  const handleGenerateBattlecard = async (event) => {
    event.preventDefault()
    setBattlecardError('')
    setBattlecardData(null)

    const channels = battlecardChannels.map((c) => c.trim()).filter(Boolean)
    if (channels.length === 0) {
      setBattlecardError('Please add at least one YouTube channel link.')
      return
    }
    if (channels.length > 4) {
      setBattlecardError('Please limit the input to 4 channels.')
      return
    }

    setIsBattlecardLoading(true)
    try {
      const params = new URLSearchParams()
      channels.forEach((channel) => params.append('channels', channel))
      params.append('max_videos_per_channel', String(maxVideosPerChannel))
      const response = await fetch(`${API_BASE}/weekly-battlecard?${params.toString()}`, {
        method: 'POST'
      })
      if (!response.ok) {
        throw new Error('Unable to generate weekly battlecard')
      }
      const data = await response.json()
      setBattlecardData(data)
    } catch (err) {
      setBattlecardError(err.message || 'Something went wrong')
    } finally {
      setIsBattlecardLoading(false)
    }
  }

  const handleClearBattlecard = () => {
    setBattlecardChannels([''])
    setMaxVideosPerChannel(4)
    setBattlecardData(null)
    setBattlecardError('')
  }

  const filteredAiProducts = useMemo(() => aiProductsData?.products || [], [aiProductsData])

  const handleAiPageChange = async (page) => {
    if (isAiProductsLoading) return
    const total = aiProductsData?.total || 0
    const maxPage = Math.max(1, Math.ceil(total / AI_PAGE_SIZE))
    const nextPage = Math.min(Math.max(page, 1), maxPage)
    setAiProductsError('')
    setIsAiProductsLoading(true)
    try {
      const offset = (nextPage - 1) * AI_PAGE_SIZE
      const response = await fetch(
        `${API_BASE}/ai-products?offset=${offset}&limit=${AI_PAGE_SIZE}&q=${encodeURIComponent(aiSearch)}`
      )
      if (!response.ok) {
        throw new Error('Unable to load products')
      }
      const data = await response.json()
      setAiProductsData(data)
      setAiPage(nextPage)
    } catch (err) {
      setAiProductsError(err.message || 'Failed to load products')
    } finally {
      setIsAiProductsLoading(false)
    }
  }

  return (
    <div className="page">
      <nav className="menu">
        <button
          className={`menu-tab ${activeMenu === 'course' ? 'active' : ''}`}
          type="button"
          onClick={() => setActiveMenu('course')}
        >
          Course Studio
        </button>
        <button
          className={`menu-tab ${activeMenu === 'battlecard' ? 'active' : ''}`}
          type="button"
          onClick={() => setActiveMenu('battlecard')}
        >
          Weekly Battlecard
        </button>
        <button
          className={`menu-tab ${activeMenu === 'ai-market' ? 'active' : ''}`}
          type="button"
          onClick={() => setActiveMenu('ai-market')}
        >
          AI Market Radar
        </button>
      </nav>

      {activeMenu === 'course' && (
        <>
          <header className="hero">
            <div>
              <p className="eyebrow">Course Studio</p>
              <h1>Turn playlists into full study courses</h1>
              <p className="subtitle">
                Build a detailed curriculum, review every lesson step-by-step, and export as PDF or PowerPoint
                for focused study sessions.
              </p>
            </div>
            <div className="hero-card">
              <form onSubmit={handleCreateCourse} className="stack">
                <label className="label">
                  Playlist URL
                  <input
                    type="url"
                    placeholder="https://www.youtube.com/playlist?list=..."
                    value={playlistUrl}
                    onChange={(event) => setPlaylistUrl(event.target.value)}
                  />
                </label>
                <button className="primary" type="submit" disabled={isSubmitting}>
                  {isSubmitting ? 'Building course...' : 'Generate course'}
                </button>
              </form>
              <div className="divider" />
              <div className="stack">
                <label className="label">
                  Or load an existing course
                  <input
                    type="text"
                    placeholder="Paste course job id"
                    value={jobId}
                    onChange={(event) => setJobId(event.target.value)}
                  />
                </label>
                <button className="secondary" type="button" onClick={handleLoadCourse} disabled={isSubmitting}>
                  Load course
                </button>
              </div>
            </div>
          </header>

          {error && <div className="alert">{error}</div>}

          {status && (
            <section className="status-card">
              <div>
                <h2>Status</h2>
                <p className="status-line">
                  <span className={`status-pill ${status.status}`}>{status.status}</span>
                  <span>{status.message || 'Working...'}</span>
                </p>
              </div>
              <div className="progress">
                <div className="progress-track">
                  <div className="progress-bar" style={{ width: `${status.progress || 0}%` }} />
                </div>
                <span>{status.progress || 0}%</span>
              </div>
              {status.job_id && (
                <p className="job-id">
                  Job ID: <span>{status.job_id}</span>
                </p>
              )}
              {showLogs && status.logs?.length > 0 && (
                <div className="logs">
                  <h3>Logs</h3>
                  <pre>{status.logs.join('\n')}</pre>
                </div>
              )}
            </section>
          )}

          {courseData && (
            <section className="course">
              <div className="course-header">
                <div>
                  <h2>{courseData.course_title || 'Course'}</h2>
                  <p className="course-hook">{courseData.hook}</p>
                  <div className="meta">
                    <span>Difficulty: {courseData.difficulty}</span>
                    <span>Estimated minutes: {courseData.estimated_total_minutes}</span>
                    <span>Videos: {courseData?.source?.videos_count ?? '-'}</span>
                  </div>
                </div>
                <div className="export">
                  <button
                    className="primary"
                    type="button"
                    onClick={() => handleDownload('pdf')}
                    disabled={!isCourseReady}
                  >
                    Download PDF
                  </button>
                  <button
                    className="secondary"
                    type="button"
                    onClick={() => handleDownload('pptx')}
                    disabled={!isCourseReady}
                  >
                    Download PowerPoint
                  </button>
                </div>
              </div>

              <div className="modules">
                {(courseData.modules || []).map((module, moduleIndex) => (
                  <details key={module.module_id || moduleIndex} className="module" open={moduleIndex === 0}>
                    <summary>
                      <div>
                        <h3>
                          Module {moduleIndex + 1}: {module.title}
                        </h3>
                        <p>{module.estimated_minutes} minutes • {module.lessons?.length || 0} lessons</p>
                      </div>
                    </summary>
                    <div className="module-body">
                      {module.objectives?.length > 0 && (
                        <div className="objectives">
                          <h4>Objectives</h4>
                          <ul>
                            {module.objectives.map((objective, index) => (
                              <li key={index}>{objective}</li>
                            ))}
                          </ul>
                        </div>
                      )}

                      <div className="lessons">
                        {(module.lessons || []).map((lesson, lessonIndex) => (
                          <details key={lesson.lesson_id || lessonIndex} className="lesson">
                            <summary>
                              <div>
                                <h4>
                                  Lesson {moduleIndex + 1}.{lessonIndex + 1}: {lesson.title}
                                </h4>
                                <p>{lesson.estimated_minutes} minutes • {lesson.difficulty}</p>
                              </div>
                            </summary>
                            <div className="lesson-body">
                              {lesson.summary && <p className="summary">{lesson.summary}</p>}
                              {lesson.video_url && (
                                <a className="video-link" href={lesson.video_url} target="_blank" rel="noreferrer">
                                  Watch video
                                </a>
                              )}
                              {lesson.learning_objectives?.length > 0 && (
                                <div>
                                  <h5>Learning objectives</h5>
                                  <ul>
                                    {lesson.learning_objectives.map((objective, index) => (
                                      <li key={index}>{objective}</li>
                                    ))}
                                  </ul>
                                </div>
                              )}
                              {lesson.study_material_markdown && (
                                <div className="reading">
                                  <h5>Study material</h5>
                                  <pre>{lesson.study_material_markdown}</pre>
                                </div>
                              )}
                              {lesson.reading_guide_markdown && (
                                <div className="reading">
                                  <h5>Reading guide</h5>
                                  <pre>{lesson.reading_guide_markdown}</pre>
                                </div>
                              )}
                            </div>
                          </details>
                        ))}
                      </div>

                      {module.quiz?.length > 0 && (
                        <div className="quiz">
                          <h4>Quiz</h4>
                          <ol>
                            {module.quiz.map((item, index) => (
                              <li key={index}>
                                <p>{item.question}</p>
                                <ul>
                                  {(item.options || []).map((option, optionIndex) => (
                                    <li key={optionIndex}>{option}</li>
                                  ))}
                                </ul>
                                <p className="answer">
                                  Answer: {typeof item.answer_index === 'number' ? item.options?.[item.answer_index] : '-'}
                                </p>
                                {item.explanation && <p className="explanation">{item.explanation}</p>}
                              </li>
                            ))}
                          </ol>
                        </div>
                      )}
                    </div>
                  </details>
                ))}
              </div>
            </section>
          )}
        </>
      )}

      {activeMenu === 'battlecard' && (
        <>
          <header className="hero">
            <div>
              <p className="eyebrow">Weekly Battlecard</p>
              <h1>Monitor competitor messaging across YouTube</h1>
              <p className="subtitle">
                Add up to four competitor channels. We summarize the latest webinars, launches, and interviews
                into an actionable weekly brief.
              </p>
            </div>
            <div className="hero-card">
              <form onSubmit={handleGenerateBattlecard} className="stack">
                <div className="stack">
                  {battlecardChannels.map((channel, index) => (
                    <label key={`${index}`} className="label">
                      Channel link {index + 1}
                      <div className="input-row">
                        <input
                          type="url"
                          placeholder="https://www.youtube.com/@competitor"
                          value={channel}
                          onChange={(event) => updateBattlecardChannel(index, event.target.value)}
                        />
                        {battlecardChannels.length > 1 && (
                          <button
                            className="ghost"
                            type="button"
                            onClick={() => removeBattlecardChannel(index)}
                          >
                            Remove
                          </button>
                        )}
                      </div>
                    </label>
                  ))}
                </div>
                <div className="input-actions">
                  <button
                    className="secondary"
                    type="button"
                    onClick={addBattlecardChannel}
                    disabled={battlecardChannels.length >= 4}
                  >
                    + Add channel
                  </button>
                  <label className="label inline">
                    Max videos / channel
                    <input
                      type="number"
                      min="1"
                      max="10"
                      value={maxVideosPerChannel}
                      onChange={(event) => setMaxVideosPerChannel(Number(event.target.value || 1))}
                    />
                  </label>
                </div>
                <div className="form-actions">
                  <button className="primary" type="submit" disabled={isBattlecardLoading}>
                    {isBattlecardLoading ? 'Building battlecard...' : 'Generate weekly battlecard'}
                  </button>
                  <button className="ghost" type="button" onClick={handleClearBattlecard}>
                    Clear & reset
                  </button>
                </div>
              </form>
            </div>
          </header>

          {battlecardError && <div className="alert">{battlecardError}</div>}

          {battlecardData && (
            <section className="battlecard">
              <div className="battlecard-header">
                <div>
                  <h2>Weekly Battlecard</h2>
                  <p className="battlecard-summary">{battlecardData.battlecard?.summary}</p>
                  <div className="meta">
                    <span>Generated: {battlecardData.generated_at?.split('T')[0]}</span>
                    <span>Channels: {battlecardData.battlecard?.channels?.length || 0}</span>
                  </div>
                </div>
                <div className="stats">
                  <div className="stat-card">
                    <p className="stat-label">Videos summarized</p>
                    <p className="stat-value">{battlecardData.battlecard?.video_summaries?.length || 0}</p>
                  </div>
                  <div className="stat-card">
                    <p className="stat-label">New features</p>
                    <p className="stat-value">{battlecardData.battlecard?.new_features?.length || 0}</p>
                  </div>
                  <div className="stat-card">
                    <p className="stat-label">Messaging shifts</p>
                    <p className="stat-value">{battlecardData.battlecard?.messaging_shifts?.length || 0}</p>
                  </div>
                </div>
                <div className="pill-stack">
                  {(battlecardData.battlecard?.concepts || []).map((concept) => (
                    <span key={concept} className="pill">
                      {concept}
                    </span>
                  ))}
                </div>
              </div>

              <div className="battlecard-grid">
                <div className="panel accent-summary">
                  <div className="panel-title">
                    <span className="dot" />
                    <h3>Video summaries</h3>
                  </div>
                  <div className="list">
                    {(battlecardData.battlecard?.video_summaries || []).map((item) => {
                      const snippet = getEvidenceSnippet(item.video_url)
                      const channelUrl = getEvidenceChannel(item.video_url)
                      return (
                        <div key={item.video_url} className="list-item">
                          <div>
                            <p className="item-title">{item.title}</p>
                            {channelUrl && <p className="item-meta">Channel: {channelUrl}</p>}
                            <p className="item-body">{item.summary}</p>
                            {snippet && <p className="item-evidence">Evidence: {snippet}</p>}
                            <p className="item-meta">Confidence: {item.confidence || 'low'}</p>
                          </div>
                          {item.video_url && (
                            <a href={item.video_url} target="_blank" rel="noreferrer" className="link">
                              Watch
                            </a>
                          )}
                        </div>
                      )
                    })}
                    {(battlecardData.battlecard?.video_summaries || []).length === 0 && (
                      <div className="empty-state">No summaries yet.</div>
                    )}
                  </div>
                </div>

                <div className="panel accent-features">
                  <div className="panel-title">
                    <span className="dot" />
                    <h3>New features</h3>
                  </div>
                  <div className="list">
                    {(battlecardData.battlecard?.new_features || []).map((item, index) => {
                      const snippet = getEvidenceSnippet(item.video_url)
                      return (
                        <div key={`${item.video_url}-${index}`} className="list-item">
                          <div>
                            <p className="item-title">{item.item}</p>
                            {item.channel_url && <p className="item-meta">Channel: {item.channel_url}</p>}
                            {snippet && <p className="item-evidence">Evidence: {snippet}</p>}
                            <p className="item-meta">Confidence: {item.confidence || 'low'}</p>
                          </div>
                          {item.video_url && (
                            <a href={item.video_url} target="_blank" rel="noreferrer" className="link">
                              Evidence
                            </a>
                          )}
                        </div>
                      )
                    })}
                    {(battlecardData.battlecard?.new_features || []).length === 0 && (
                      <div className="empty-state">No new feature updates detected.</div>
                    )}
                  </div>
                </div>

                <div className="panel accent-pricing">
                  <div className="panel-title">
                    <span className="dot" />
                    <h3>Pricing changes</h3>
                  </div>
                  <div className="list">
                    {(battlecardData.battlecard?.pricing_changes || []).map((item, index) => {
                      const snippet = getEvidenceSnippet(item.video_url)
                      return (
                        <div key={`${item.video_url}-${index}`} className="list-item">
                          <div>
                            <p className="item-title">{item.item}</p>
                            {item.channel_url && <p className="item-meta">Channel: {item.channel_url}</p>}
                            {snippet && <p className="item-evidence">Evidence: {snippet}</p>}
                            <p className="item-meta">Confidence: {item.confidence || 'low'}</p>
                          </div>
                          {item.video_url && (
                            <a href={item.video_url} target="_blank" rel="noreferrer" className="link">
                              Evidence
                            </a>
                          )}
                        </div>
                      )
                    })}
                    {(battlecardData.battlecard?.pricing_changes || []).length === 0 && (
                      <div className="empty-state">No pricing changes detected.</div>
                    )}
                  </div>
                </div>

                <div className="panel accent-messaging">
                  <div className="panel-title">
                    <span className="dot" />
                    <h3>Messaging shifts</h3>
                  </div>
                  <div className="list">
                    {(battlecardData.battlecard?.messaging_shifts || []).map((item, index) => {
                      const snippet = getEvidenceSnippet(item.video_url)
                      return (
                        <div key={`${item.video_url}-${index}`} className="list-item">
                          <div>
                            <p className="item-title">{item.item}</p>
                            {item.channel_url && <p className="item-meta">Channel: {item.channel_url}</p>}
                            {snippet && <p className="item-evidence">Evidence: {snippet}</p>}
                            <p className="item-meta">Confidence: {item.confidence || 'low'}</p>
                          </div>
                          {item.video_url && (
                            <a href={item.video_url} target="_blank" rel="noreferrer" className="link">
                              Evidence
                            </a>
                          )}
                        </div>
                      )
                    })}
                    {(battlecardData.battlecard?.messaging_shifts || []).length === 0 && (
                      <div className="empty-state">No messaging shifts detected.</div>
                    )}
                  </div>
                </div>
              </div>

              <div className="battlecard-footer">
                {battlecardData.battlecard?.sentiment_shift?.status &&
                  battlecardData.battlecard.sentiment_shift.status !== 'unknown' && (
                    <div className="panel accent-sentiment">
                      <div className="panel-title">
                        <span className="dot" />
                        <h3>Sentiment shift</h3>
                      </div>
                      <p className="item-body">{battlecardData.battlecard?.sentiment_shift?.summary}</p>
                      <p className="item-meta">
                        Status: {battlecardData.battlecard?.sentiment_shift?.status} · Confidence:{' '}
                        {battlecardData.battlecard?.sentiment_shift?.confidence}
                      </p>
                    </div>
                  )}
                <div className="panel accent-channels">
                  <div className="panel-title">
                    <span className="dot" />
                    <h3>Channels scanned</h3>
                  </div>
                  <div className="list">
                    {(battlecardData.battlecard?.channels || []).map((item) => (
                      <div key={item.channel_url} className="list-item">
                        <div>
                          <p className="item-title">{item.channel_url}</p>
                          <p className="item-meta">{item.notes}</p>
                        </div>
                        <a href={item.channel_url} target="_blank" rel="noreferrer" className="link">
                          Open
                        </a>
                      </div>
                    ))}
                    {(battlecardData.battlecard?.channels || []).length === 0 && (
                      <div className="empty-state">No channels scanned.</div>
                    )}
                  </div>
                </div>
              </div>
            </section>
          )}
        </>
      )}

      {activeMenu === 'ai-market' && (
        <>
          <header className="hero">
            <div>
              <p className="eyebrow">AI Market Radar</p>
              <h1>All AI products under one umbrella</h1>
              <p className="subtitle">
                Browse summaries, features, pricing, and related videos across the AI product landscape.
              </p>
            </div>
            <div className="hero-card">
              <div className="stack">
                <label className="label">
                  Search products
                  <input
                    type="text"
                    placeholder="Search by name, feature, category..."
                    value={aiSearch}
                    onChange={(event) => setAiSearch(event.target.value)}
                  />
                </label>
                <div className="input-actions">
                  <div className="meta-row">
                    {isAiProductsLoading ? (
                      <span className="meta-pill">Loading products...</span>
                    ) : (
                      <>
                        <span className="meta-pill">{aiProductsData?.total || filteredAiProducts.length} products</span>
                        {aiProductsData?.generated_at && (
                          <span className="meta-pill">Updated {aiProductsData.generated_at.split('T')[0]}</span>
                        )}
                        {aiProductsData?.total && (
                          <span className="meta-pill">
                            Page {aiPage} of {Math.max(1, Math.ceil(aiProductsData.total / AI_PAGE_SIZE))}
                          </span>
                        )}
                      </>
                    )}
                  </div>
                  <div className="form-actions">
                    <button className="ghost" type="button" onClick={() => setAiSearch('')}>
                      Clear search
                    </button>
                    <button className="secondary" type="button" onClick={handleSyncAiProducts}>
                      Sync now
                    </button>
                    <button className="secondary" type="button" onClick={handleSyncZapierList}>
                      Load Zapier list
                    </button>
                    <button className="primary" type="button" onClick={handleSyncSources}>
                      Sync all sources
                    </button>
                  </div>
                </div>
              </div>
            </div>
          </header>

          {aiProductsError && <div className="alert">{aiProductsError}</div>}

          <section className="ai-market">
            {filteredAiProducts.map((product) => (
              <article key={product.name} className="ai-card">
                <div>
                  <div className="ai-card-header">
                    <h3>{product.name}</h3>
                    {product.category && <span className="pill">{product.category}</span>}
                  </div>
                  <p className="item-body">{product.summary}</p>
                  {product.value_proposition && (
                    <p className="item-evidence">What it does: {product.value_proposition}</p>
                  )}
                  {product.pricing && <p className="item-meta">Pricing: {product.pricing}</p>}
                  {product.source && <p className="item-meta">Source: {product.source}</p>}
                </div>
                {product.features?.length > 0 && (
                  <div>
                    <p className="item-title">Key features</p>
                    <ul className="feature-list">
                      {product.features.map((feature) => (
                        <li key={feature}>{feature}</li>
                      ))}
                    </ul>
                  </div>
                )}
                {product.tags?.length > 0 && (
                  <div className="pill-stack">
                    {product.tags.slice(0, 4).map((tag) => (
                      <span key={tag} className="tag">
                        {tag}
                      </span>
                    ))}
                    {product.tags.length > 4 && (
                      <span className="tag tag-muted">+{product.tags.length - 4}</span>
                    )}
                  </div>
                )}
                <div className="ai-links">
                  {product.website_url && (
                    <a href={product.website_url} target="_blank" rel="noreferrer" className="link">
                      Website
                    </a>
                  )}
                  {product.video_url && (
                    <a href={product.video_url} target="_blank" rel="noreferrer" className="link">
                      Video
                    </a>
                  )}
                  {product.source_url && (
                    <a href={product.source_url} target="_blank" rel="noreferrer" className="link">
                      Source
                    </a>
                  )}
                </div>
              </article>
            ))}
            {!isAiProductsLoading && filteredAiProducts.length === 0 && (
              <div className="empty-state">No products match your search.</div>
            )}
          </section>
          {!aiSearch && aiProductsData?.total > AI_PAGE_SIZE && (
            <div className="pagination">
              <button
                className="ghost"
                type="button"
                onClick={() => handleAiPageChange(aiPage - 1)}
                disabled={isAiProductsLoading || aiPage <= 1}
              >
                Prev
              </button>
              <span className="item-meta">
                Page {aiPage} of {Math.max(1, Math.ceil(aiProductsData.total / AI_PAGE_SIZE))}
              </span>
              <button
                className="ghost"
                type="button"
                onClick={() => handleAiPageChange(aiPage + 1)}
                disabled={isAiProductsLoading || aiPage >= Math.ceil(aiProductsData.total / AI_PAGE_SIZE)}
              >
                Next
              </button>
            </div>
          )}
        </>
      )}
    </div>
  )
}

export default App
