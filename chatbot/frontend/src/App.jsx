import { useState, useRef, useEffect } from 'react'
import ReactMarkdown from 'react-markdown'

function App() {
  const [messages, setMessages] = useState([])
  const [inputValue, setInputValue] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const messagesEndRef = useRef(null)

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }

  useEffect(() => {
    scrollToBottom()
  }, [messages])

  const examplePrompts = [
    'Tell me about Spring Fest',
    'Main Building History',
    "Explain 'Hall Tempo'",
    'Life at Nehru Museum'
  ]

  const handleSendMessage = async (messageText) => {
    const query = messageText || inputValue
    if (!query.trim()) return

    // Add user message to chat
    const userMessage = {
      type: 'user',
      content: query
    }
    setMessages(prev => [...prev, userMessage])
    setInputValue('')
    setIsLoading(true)

    try {
      const response = await fetch('http://localhost:8000/got/query', {
        method: 'POST',
        headers: {
          'accept': 'application/json',
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ query })
      })

      const data = await response.json()
      
      // Add bot response to chat
      const botMessage = {
        type: 'bot',
        content: data.answer || data.error || 'No response received',
        sources: data.sources || [],
        chunksRetrieved: data.chunks_retrieved,
        error: data.error
      }
      setMessages(prev => [...prev, botMessage])
    } catch (error) {
      const errorMessage = {
        type: 'bot',
        content: `Error: ${error.message}`,
        isError: true
      }
      setMessages(prev => [...prev, errorMessage])
    } finally {
      setIsLoading(false)
    }
  }

  const handleKeyPress = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSendMessage()
    }
  }

  return (
    <div className="h-screen flex flex-col bg-graphmind-dark">
      <header className="flex justify-between items-center px-4 md:px-8 py-3 md:py-4 border-b border-gray-800 flex-shrink-0">
        <div className="flex items-center gap-2 md:gap-3">
          <div className="flex items-center justify-center">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" className="md:w-6 md:h-6">
              <circle cx="12" cy="12" r="10" stroke="#3B82F6" strokeWidth="2"/>
              <circle cx="12" cy="12" r="6" stroke="#3B82F6" strokeWidth="2"/>
              <circle cx="12" cy="12" r="2" fill="#3B82F6"/>
            </svg>
          </div>
          <span className="text-lg md:text-xl font-semibold text-graphmind-blue">GraphMind</span>
        </div>
        <div className="text-xs md:text-sm text-gray-400 tracking-wider">IIT KHARAGPUR</div>
      </header>

      <main className="flex-1 flex flex-col overflow-y-auto p-4 md:p-8 min-h-0">
        {messages.length === 0 ? (
          <div className="max-w-4xl mx-auto text-center py-6 md:py-8">
            <div className="inline-flex p-4 md:p-5 bg-[#1a2332] rounded-2xl mb-4 md:mb-6">
              <svg width="48" height="48" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" className="md:w-16 md:h-16">
                <circle cx="12" cy="12" r="10" stroke="#3B82F6" strokeWidth="1.5"/>
                <path d="M12 6v6l4 2" stroke="#3B82F6" strokeWidth="1.5" strokeLinecap="round"/>
              </svg>
            </div>
            <h1 className="text-3xl md:text-4xl lg:text-5xl font-semibold mb-3 md:mb-4 text-white">How can I help you today?</h1>
            <p className="text-sm md:text-base lg:text-lg text-blue-400 leading-relaxed max-w-2xl mx-auto mb-6 md:mb-8 px-4">
              I'm GraphMind, your intelligent companion for everything IIT Kharagpur. Ask me about academics, culture, or campus history.
            </p>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3 md:gap-4 max-w-3xl mx-auto px-4">
              {examplePrompts.map((prompt, index) => (
                <button
                  key={index}
                  className="bg-[#0f1419] border border-[#1f2937] rounded-xl p-4 md:p-5 text-left cursor-pointer transition-all duration-200 hover:bg-[#1a1f2e] hover:border-graphmind-blue hover:-translate-y-0.5"
                  onClick={() => handleSendMessage(prompt)}
                >
                  <div className="text-sm md:text-base font-medium text-white mb-1">{prompt}</div>
                  <div className="text-xs text-gray-600">Click to ask GraphMind</div>
                </button>
              ))}
            </div>
          </div>
        ) : (
          <div className="max-w-4xl mx-auto w-full px-4">
            <div className="flex flex-col gap-4 md:gap-6">
              {messages.map((message, index) => (
                <div key={index} className={`flex gap-3 md:gap-4 items-start ${message.type === 'user' ? 'flex-row-reverse' : ''}`}>
                  {message.type === 'bot' && (
                    <div className="flex-shrink-0 w-7 h-7 md:w-8 md:h-8 rounded-lg overflow-hidden">
                      <svg width="32" height="32" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                        <rect width="24" height="24" rx="4" fill="#1E40AF"/>
                        <circle cx="12" cy="12" r="6" stroke="white" strokeWidth="1.5"/>
                      </svg>
                    </div>
                  )}
                  <div className={`flex-1 max-w-[85%] md:max-w-[80%] ${message.type === 'user' ? 'flex flex-col items-end' : ''}`}>
                    {message.type === 'bot' && (
                      <div className="text-xs md:text-sm mb-1 md:mb-2 text-gray-400">
                        <strong>GraphMind</strong>
                      </div>
                    )}
                    {message.type === 'user' && (
                      <div className="bg-graphmind-blue text-white text-xs font-semibold px-3 py-1.5 rounded-full mb-2">
                        YOU
                      </div>
                    )}
                    <div className={`${message.type === 'user' ? 'bg-blue-600 text-white rounded-xl rounded-tr-none' : 'bg-graphmind-card text-gray-200 rounded-xl rounded-tl-none'} px-4 md:px-5 py-3 md:py-4 text-sm md:text-base leading-relaxed`}>
                      {message.type === 'bot' ? (
                        <ReactMarkdown
                          components={{
                            p: ({children}) => <p className="mb-2 last:mb-0">{children}</p>,
                            ul: ({children}) => <ul className="list-disc list-inside mb-2">{children}</ul>,
                            ol: ({children}) => <ol className="list-decimal list-inside mb-2">{children}</ol>,
                            li: ({children}) => <li className="mb-1">{children}</li>,
                            code: ({inline, children}) => 
                              inline ? <code className="bg-gray-800 px-1.5 py-0.5 rounded text-blue-300">{children}</code> 
                              : <code className="block bg-gray-800 p-3 rounded my-2 overflow-x-auto">{children}</code>,
                            strong: ({children}) => <strong className="font-bold text-blue-300">{children}</strong>,
                            a: ({href, children}) => <a href={href} target="_blank" rel="noopener noreferrer" className="text-blue-400 hover:text-blue-300 underline">{children}</a>,
                            h1: ({children}) => <h1 className="text-2xl font-bold mb-3 mt-2">{children}</h1>,
                            h2: ({children}) => <h2 className="text-xl font-bold mb-2 mt-2">{children}</h2>,
                            h3: ({children}) => <h3 className="text-lg font-bold mb-2 mt-2">{children}</h3>,
                          }}
                        >
                          {message.content}
                        </ReactMarkdown>
                      ) : (
                        <div className="whitespace-pre-wrap">{message.content}</div>
                      )}
                    </div>
                    {message.type === 'bot' && (
                      <div className="mt-2 pl-3 md:pl-5 space-y-1">
                        {message.sources && message.sources.length > 0 && (
                          <div className="flex flex-wrap gap-1 items-center text-xs">
                            <span className="text-gray-500">Sources:</span>
                            {message.sources.map((source, idx) => {
                              const wikiUrl = `https://wiki.metakgp.org/w/${source.replace(/ /g, '_')}`;
                              return (
                                <a
                                  key={idx}
                                  href={wikiUrl}
                                  target="_blank"
                                  rel="noopener noreferrer"
                                  className="group relative inline-flex items-center gap-1 px-2 py-1 bg-blue-900/20 hover:bg-blue-900/40 text-blue-400 rounded-md transition-colors"
                                  title={source}
                                >
                                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                                    <path d="M12 2L2 7l10 5 10-5-10-5z" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                                    <path d="M2 17l10 5 10-5M2 12l10 5 10-5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                                  </svg>
                                  <span className="max-w-[120px] truncate">{source}</span>
                                  {/* Tooltip */}
                                  <div className="invisible group-hover:visible absolute bottom-full left-1/2 transform -translate-x-1/2 mb-2 px-3 py-2 bg-gray-900 text-white text-xs rounded-lg shadow-lg whitespace-nowrap z-10 pointer-events-none">
                                    <div className="font-medium mb-1">{source}</div>
                                    <div className="text-blue-300">Click to view on MetaKGP Wiki →</div>
                                    {/* Arrow */}
                                    <div className="absolute top-full left-1/2 transform -translate-x-1/2 -mt-1">
                                      <div className="border-4 border-transparent border-t-gray-900"></div>
                                    </div>
                                  </div>
                                </a>
                              );
                            })}
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                </div>
              ))}
              {isLoading && (
                <div className="flex gap-3 md:gap-4 items-start">
                  <div className="flex-shrink-0 w-7 h-7 md:w-8 md:h-8 rounded-lg overflow-hidden">
                    <svg width="32" height="32" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                      <rect width="24" height="24" rx="4" fill="#1E40AF"/>
                      <circle cx="12" cy="12" r="6" stroke="white" strokeWidth="1.5"/>
                    </svg>
                  </div>
                  <div className="flex-1">
                    <div className="flex gap-2 p-4">
                      <span className="w-2 h-2 bg-graphmind-blue rounded-full animate-bounce [animation-delay:-0.32s]"></span>
                      <span className="w-2 h-2 bg-graphmind-blue rounded-full animate-bounce [animation-delay:-0.16s]"></span>
                      <span className="w-2 h-2 bg-graphmind-blue rounded-full animate-bounce"></span>
                    </div>
                  </div>
                </div>
              )}
              <div ref={messagesEndRef} />
            </div>
          </div>
        )}
      </main>

      <footer className="px-4 md:px-8 py-3 md:py-4 pb-4 md:pb-6 border-t border-gray-800 flex-shrink-0">
        <div className="max-w-4xl mx-auto mb-2 md:mb-3 flex gap-2 md:gap-3 items-center bg-[#0f1419] rounded-full px-4 md:px-6 py-2 md:py-3 border border-[#1f2937] focus-within:border-graphmind-blue transition-colors">
          <input
            type="text"
            className="flex-1 bg-transparent border-none outline-none text-white text-sm md:text-base placeholder-gray-600"
            placeholder="Message GraphMind..."
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            onKeyPress={handleKeyPress}
            disabled={isLoading}
          />
          <button
            className="w-8 h-8 md:w-10 md:h-10 rounded-full border-none bg-transparent text-graphmind-blue flex items-center justify-center cursor-pointer transition-all duration-200 flex-shrink-0 hover:text-blue-400 disabled:text-gray-700 disabled:cursor-not-allowed"
            onClick={() => handleSendMessage()}
            disabled={isLoading || !inputValue.trim()}
          >
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" className="md:w-6 md:h-6">
              <path d="M22 2L11 13M22 2l-7 20-4-9-9-4 20-7z" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
            </svg>
          </button>
        </div>
        <div className="text-center text-xs md:text-sm text-graphmind-blue tracking-[0.2em] font-medium">
          YOGAH KARMASU KAUSHALAM
        </div>
      </footer>
    </div>
  )
}

export default App
