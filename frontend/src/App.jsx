import { useState, useEffect } from 'react'
import '@cloudscape-design/global-styles/index.css'
import './LogOutput.css'
import {
  AppLayout,
  ContentLayout,
  Header,
  SpaceBetween,
  Container,
  Grid,
  Button,
  FormField,
  Select,
  Slider,
  Input,
  RadioGroup,
  FileUpload,
  Alert,
  Box,
  ExpandableSection,
  Modal,
  Link,
} from '@cloudscape-design/components'
import axios from 'axios'

const API_BASE_URL = ''

function App() {
  // State for form inputs
  const [imageFile, setImageFile] = useState([])
  const [method, setMethod] = useState({ value: 'rf-detr', label: 'RF-DETR' })
  const [objectName, setObjectName] = useState('')
  const [confidence, setConfidence] = useState(0.5)
  const [aspectMode, setAspectMode] = useState('none')
  const [customAspect, setCustomAspect] = useState('')
  const [padding, setPadding] = useState(8)
  const [threshold, setThreshold] = useState(240)
  const [selectedObject, setSelectedObject] = useState(null)

  // State for results
  const [visualizationUrl, setVisualizationUrl] = useState(null)
  const [croppedUrl, setCroppedUrl] = useState(null)
  const [infoText, setInfoText] = useState('')
  const [detections, setDetections] = useState([])
  const [isProcessing, setIsProcessing] = useState(false)
  const [errorMessage, setErrorMessage] = useState('')
  const [batchFiles, setBatchFiles] = useState([])

  // State for image modal
  const [modalVisible, setModalVisible] = useState(false)
  const [modalImageUrl, setModalImageUrl] = useState('')
  const [modalImageTitle, setModalImageTitle] = useState('')

  // State to track if sample image should be auto-processed
  const [shouldAutoProcess, setShouldAutoProcess] = useState(false)

  // Clear detections when detection method changes
  useEffect(() => {
    // Clear stored detections so new method will be used
    setDetections([])
    setSelectedObject(null)
  }, [method])

  const detectionMethods = [
    { value: 'rf-detr', label: 'RF-DETR' },
    { value: 'rt-detr', label: 'RT-DETR' },
    { value: 'detr', label: 'DETR' },
    { value: 'yolo', label: 'YOLO' },
    { value: 'contour', label: 'Contour' },
    { value: 'saliency', label: 'Saliency' },
    { value: 'edge', label: 'Edge' },
    { value: 'grabcut', label: 'GrabCut' },
  ]

  const aspectModes = [
    { value: 'none', label: 'None (use detected bounds)' },
    { value: 'original', label: 'Keep Original Aspect Ratio' },
    { value: 'custom', label: 'Custom Aspect Ratio' },
  ]

  // Load sample image on component mount
  useEffect(() => {
    const loadSampleImage = async () => {
      try {
        const response = await fetch('/sample_images/sample_image_00001.jpg')
        if (!response.ok) {
          console.warn('Sample image not available')
          return
        }
        const blob = await response.blob()
        const file = new File([blob], 'sample_image_00001.jpg', { type: 'image/jpeg' })
        setImageFile([file])
        setShouldAutoProcess(true) // Trigger auto-processing
      } catch (error) {
        console.error('Failed to load sample image:', error)
        // Fail silently - user can upload their own image
      }
    }

    loadSampleImage()
  }, []) // Empty dependency array = run once on mount

  // Auto-process sample image after it's loaded
  useEffect(() => {
    if (shouldAutoProcess && imageFile.length > 0) {
      setShouldAutoProcess(false) // Reset flag to prevent re-processing on user uploads
      handleProcessImage()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [imageFile, shouldAutoProcess]) // Run when imageFile or shouldAutoProcess changes

  const handleProcessImage = async (useSelectedIndex = false, overrideSelectedObject = null) => {
    if (imageFile.length === 0) {
      setErrorMessage('Please upload an image first.')
      return
    }

    setIsProcessing(true)
    setErrorMessage('')

    const formData = new FormData()
    formData.append('file', imageFile[0])
    formData.append('method', method.value)
    formData.append('object_name', objectName)
    formData.append('confidence', confidence)
    formData.append('aspect_mode', aspectMode)
    formData.append('custom_aspect_ratio', customAspect)
    formData.append('padding', padding)
    formData.append('threshold', threshold)

    // If using selected index and we have detections, pass them to avoid re-running detection
    const objectToUse = overrideSelectedObject || selectedObject
    if (useSelectedIndex && objectToUse && detections.length > 0) {
      formData.append('selected_index', objectToUse.value)
      formData.append('stored_detections', JSON.stringify(detections))
    }

    try {
      const response = await axios.post(`${API_BASE_URL}/api/process`, formData, {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
      })

      const data = response.data
      // Add timestamp to prevent browser caching
      const timestamp = new Date().getTime()
      setVisualizationUrl(`${API_BASE_URL}${data.visualization_url}?t=${timestamp}`)
      setCroppedUrl(`${API_BASE_URL}${data.cropped_url}?t=${timestamp}`)
      setInfoText(data.info_text)
      setDetections(data.detections || [])

      // If we have multiple detections and this is a new processing (not re-selection)
      // Set the selected object to the one with matching bounds (the auto-selected one)
      if (!useSelectedIndex && data.detections && data.detections.length > 1 && data.bounds) {
        const selectedIdx = data.detections.findIndex(
          det => det.box[0] === data.bounds[0] && det.box[1] === data.bounds[1] &&
            det.box[2] === data.bounds[2] && det.box[3] === data.bounds[3]
        )
        if (selectedIdx >= 0) {
          setSelectedObject({
            value: String(selectedIdx),
            label: `${selectedIdx}: ${data.detections[selectedIdx].label} (${data.detections[selectedIdx].confidence.toFixed(2)})`
          })
        }
      }
    } catch (error) {
      setErrorMessage(error.response?.data?.detail || 'Error processing image')
      console.error('Error:', error)
    } finally {
      setIsProcessing(false)
    }
  }

  // Handle object selection change - automatically re-process with selected object
  const handleObjectSelectionChange = async (detail) => {
    const newSelection = detail.selectedOption
    setSelectedObject(newSelection)
    // Automatically re-process with the newly selected object
    // Pass it directly to avoid state update delay
    await handleProcessImage(true, newSelection)
  }

  // Handle image click to open modal
  const handleImageClick = (imageUrl, title) => {
    setModalImageUrl(imageUrl)
    setModalImageTitle(title)
    setModalVisible(true)
  }

  const handleBatchCrop = async () => {
    if (imageFile.length === 0) {
      setErrorMessage('Please upload an image first.')
      return
    }

    if (!['yolo', 'detr', 'rt-detr'].includes(method.value)) {
      setErrorMessage('Batch crop only works with YOLO, DETR, or RT-DETR methods.')
      return
    }

    setIsProcessing(true)
    setErrorMessage('')

    const formData = new FormData()
    formData.append('file', imageFile[0])
    formData.append('method', method.value)
    formData.append('object_name', objectName)
    formData.append('confidence', confidence)
    formData.append('aspect_mode', aspectMode)
    formData.append('custom_aspect_ratio', customAspect)
    formData.append('padding', padding)
    formData.append('threshold', threshold)

    try {
      const response = await axios.post(`${API_BASE_URL}/api/batch-crop`, formData, {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
      })

      const data = response.data
      setBatchFiles(data.files)
      setInfoText(data.message)
    } catch (error) {
      setErrorMessage(error.response?.data?.detail || 'Error during batch crop')
      console.error('Error:', error)
    } finally {
      setIsProcessing(false)
    }
  }

  // Clean up log formatting and remove timestamps
  const removeTimestamps = (text) => {
    if (!text) return text

    const lines = text.split('\n')
    const cleanedLines = []

    for (let i = 0; i < lines.length; i++) {
      let line = lines[i].trim()

      // Remove timestamps at the start of lines (after trimming)
      // More permissive patterns to catch various timestamp formats
      line = line
        .replace(/^\[[^\]]+\]\s*/, '') // Remove any [bracketed content] at start
        .replace(/^\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}[.,]\d+\s*[-:]?\s*/, '')
        .replace(/^\d{2}:\d{2}:\d{2}[.,]?\d*\s*[-:]?\s*/, '')
        .replace(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[^\s]*\s*/, '')
        .trim()

      // Check if this line is a separator line (all = or - characters)
      if (/^[=\-]{10,}$/.test(line)) {
        // Check if the next line has content (section title)
        if (i + 1 < lines.length) {
          const nextLine = lines[i + 1].trim()
          // Check if line after next is also a separator
          if (i + 2 < lines.length && /^[=\-]{10,}$/.test(lines[i + 2].trim()) && nextLine) {
            // This is a header pattern, make the title bold
            cleanedLines.push(`**${nextLine}**`)
            i += 2 // Skip the title and bottom separator
            continue
          }
        }
        // Otherwise skip standalone separator lines
        continue
      }

      // Add the line if it's not empty or if we want to preserve spacing
      if (line || cleanedLines.length > 0) {
        cleanedLines.push(line)
      }
    }

    return cleanedLines.join('\n')
  }

  // Render text with markdown-style bold
  const renderFormattedText = (text) => {
    if (!text) return text

    const lines = text.split('\n')
    return lines.map((line, lineIndex) => {
      // Check if line contains **bold** markdown
      if (line.includes('**')) {
        const parts = []
        let lastIndex = 0
        const boldRegex = /\*\*([^*]+)\*\*/g
        let match

        while ((match = boldRegex.exec(line)) !== null) {
          // Add text before the bold part
          if (match.index > lastIndex) {
            parts.push(line.substring(lastIndex, match.index))
          }
          // Add bold part
          parts.push(<strong key={`${lineIndex}-${match.index}`}>{match[1]}</strong>)
          lastIndex = match.index + match[0].length
        }

        // Add remaining text
        if (lastIndex < line.length) {
          parts.push(line.substring(lastIndex))
        }

        return (
          <div key={lineIndex}>
            {parts.length > 0 ? parts : line}
          </div>
        )
      }

      return <div key={lineIndex}>{line || '\u00A0'}</div>
    })
  }

  return (
    <>
      <AppLayout
        navigationHide
        toolsHide
        content={
          <ContentLayout
            header={
              <SpaceBetween size="m">
                <Header variant="h1">
                  Interactive Cropping
                </Header>
                <Box variant="p">
                  Upload your images and let AI identify objects,
                  then crop with customizable padding and aspect ratios. Download individual cropped images
                  or batch process multiple objects at once.
                </Box>
              </SpaceBetween>
            }
          >
            <SpaceBetween size="l">
              {errorMessage && (
                <Alert type="error" dismissible onDismiss={() => setErrorMessage('')}>
                  {errorMessage}
                </Alert>
              )}

              <Grid gridDefinition={[{ colspan: 4 }, { colspan: 8 }]}>
                {/* Left Column - Controls */}
                <SpaceBetween size="l">
                  <Container header={<Header variant="h2">1. Input</Header>}>
                    <div style={{ minHeight: '150px' }}>
                      <FormField label="Upload Image (JPEG/PNG/WebP only)">
                        <FileUpload
                          onChange={({ detail }) => {
                            setImageFile(detail.value)
                            // Reset detection-related state when new image is selected
                            if (detail.value.length > 0) {
                              setDetections([])
                              setSelectedObject(null)
                              setVisualizationUrl(null)
                              setCroppedUrl(null)
                              setInfoText('')
                              setBatchFiles([])
                              setErrorMessage('')
                            }
                          }}
                          value={imageFile}
                          accept="image/jpeg,image/jpg,image/png,image/webp"
                          i18nStrings={{
                            uploadButtonText: e => (e ? 'Choose files' : 'Choose file'),
                            dropzoneText: e => (e ? 'Drop files to upload' : 'Drop file to upload'),
                            removeFileAriaLabel: e => `Remove file ${e + 1}`,
                            limitShowFewer: 'Show fewer files',
                            limitShowMore: 'Show more files',
                            errorIconAriaLabel: 'Error',
                          }}
                          showFileLastModified
                          showFileSize
                          showFileThumbnail
                          tokenLimit={3}
                          constraintText="Supported formats: JPEG, PNG, WebP"
                        />
                      </FormField>
                    </div>
                  </Container>

                  <Container header={<Header variant="h2">Detection Options</Header>}>
                    <SpaceBetween size="l">
                      <FormField label="Detection Method" description="Select the object detection algorithm to use">
                        <Select
                          selectedOption={method}
                          onChange={({ detail }) => setMethod(detail.selectedOption)}
                          options={detectionMethods}
                        />
                      </FormField>

                      <FormField label="Confidence Threshold" description="YOLO/DETR: Minimum confidence for detected objects">
                        <Slider
                          onChange={({ detail }) => setConfidence(detail.value)}
                          value={confidence}
                          min={0.1}
                          max={1.0}
                          step={0.05}
                          valueFormatter={value => value.toFixed(2)}
                        />
                      </FormField>

                      {detections.length > 1 && (
                        <FormField label="Select Detected Object" description="Choose which object to crop when multiple are detected">
                          <Select
                            selectedOption={selectedObject}
                            onChange={({ detail }) => handleObjectSelectionChange(detail)}
                            options={detections.map((det, idx) => ({
                              value: String(idx),
                              label: `${idx}: ${det.label} (${det.confidence.toFixed(2)})`,
                            }))}
                            placeholder="Select an object"
                          />
                        </FormField>
                      )}

                      <FormField
                        label="Object to Detect (optional)"
                        description="YOLO/DETR: Leave empty to detect the largest/most confident object"
                      >
                        <Input
                          value={objectName}
                          onChange={({ detail }) => setObjectName(detail.value)}
                          placeholder="e.g., couch, person, chair"
                        />
                      </FormField>

                      <FormField
                        label="Binary Threshold"
                        description="Contour: Control foreground/background separation"
                      >
                        <Slider
                          onChange={({ detail }) => setThreshold(detail.value)}
                          value={threshold}
                          min={50}
                          max={250}
                          step={5}
                        />
                      </FormField>

                      <FormField label="Aspect Ratio" description="Choose how to handle the final crop aspect ratio">
                        <RadioGroup
                          onChange={({ detail }) => setAspectMode(detail.value)}
                          value={aspectMode}
                          items={aspectModes}
                        />
                      </FormField>

                      {aspectMode === 'custom' && (
                        <FormField
                          label="Custom Aspect Ratio"
                          description="Enter ratio as width:height (16:9) or decimal (1.78)"
                        >
                          <Input
                            value={customAspect}
                            onChange={({ detail }) => setCustomAspect(detail.value)}
                            placeholder="e.g., 16:9, 4:3, 1.5, or 2.35"
                          />
                        </FormField>
                      )}

                      <FormField label="Padding (%)" description="Add padding around the detected object">
                        <Slider
                          onChange={({ detail }) => setPadding(detail.value)}
                          value={padding}
                          min={0}
                          max={50}
                          step={1}
                        />
                      </FormField>

                      <SpaceBetween size="s">
                        <Button
                          variant="primary"
                          onClick={handleProcessImage}
                          loading={isProcessing}
                          fullWidth
                        >
                          Process Image
                        </Button>

                        <Button
                          onClick={handleBatchCrop}
                          loading={isProcessing}
                          fullWidth
                        >
                          Batch Crop All Objects
                        </Button>
                      </SpaceBetween>
                    </SpaceBetween>
                  </Container>

                  {batchFiles.length > 0 && (
                    <Container header={<Header variant="h2">Download Cropped Images</Header>}>
                      <SpaceBetween size="s">
                        {batchFiles.map((file, idx) => (
                          <Button
                            key={idx}
                            href={`${API_BASE_URL}${file}`}
                            target="_blank"
                            iconName="download"
                          >
                            Download {file.split('/').pop()}
                          </Button>
                        ))}
                      </SpaceBetween>
                    </Container>
                  )}
                </SpaceBetween>

                {/* Right Column - Results */}
                <SpaceBetween size="l">
                  <Grid gridDefinition={[{ colspan: 6 }, { colspan: 6 }]}>
                    <Container header={<Header variant="h2">2. Analysis</Header>}>
                      <div style={{ minHeight: '150px' }}>
                        {visualizationUrl ? (
                          <Box textAlign="center">
                            <img
                              src={visualizationUrl}
                              alt="Detection Preview"
                              style={{
                                maxWidth: '100%',
                                height: 'auto',
                                cursor: 'pointer',
                                transition: 'transform 0.2s, box-shadow 0.2s',
                              }}
                              onClick={() => handleImageClick(visualizationUrl, 'Detection Analysis')}
                              onMouseOver={(e) => {
                                e.currentTarget.style.transform = 'scale(1.02)'
                                e.currentTarget.style.boxShadow = '0 4px 8px rgba(0,0,0,0.2)'
                              }}
                              onMouseOut={(e) => {
                                e.currentTarget.style.transform = 'scale(1)'
                                e.currentTarget.style.boxShadow = 'none'
                              }}
                              title="Click to enlarge"
                            />
                            <Box variant="small" color="text-status-info">
                              Green = Selected, Yellow = Other Detections • Click to enlarge
                            </Box>
                          </Box>
                        ) : (
                          <Box textAlign="center" color="text-status-inactive">
                            No visualization yet. Upload an image and click Process.
                          </Box>
                        )}
                      </div>
                    </Container>

                    <Container header={<Header variant="h2">3. Result</Header>}>
                      <div style={{ minHeight: '150px', paddingBottom: '20px', overflow: 'visible' }}>
                        {croppedUrl ? (
                          <Box textAlign="center">
                            <img
                              src={croppedUrl}
                              alt="Cropped Image"
                              style={{
                                maxWidth: '100%',
                                maxHeight: '400px',
                                height: 'auto',
                                cursor: 'pointer',
                                transition: 'transform 0.2s, box-shadow 0.2s',
                                display: 'block',
                                margin: '0 auto',
                              }}
                              onClick={() => handleImageClick(croppedUrl, 'Cropped Result')}
                              onMouseOver={(e) => {
                                e.currentTarget.style.transform = 'scale(1.02)'
                                e.currentTarget.style.boxShadow = '0 4px 8px rgba(0,0,0,0.2)'
                              }}
                              onMouseOut={(e) => {
                                e.currentTarget.style.transform = 'scale(1)'
                                e.currentTarget.style.boxShadow = 'none'
                              }}
                              title="Click to enlarge"
                            />
                            <Box
                              variant="small"
                              color="text-status-info"
                              margin={{ top: 's' }}
                              padding={{ bottom: 's' }}
                            >
                              Click to enlarge
                            </Box>
                          </Box>
                        ) : (
                          <Box textAlign="center" color="text-status-inactive">
                            No cropped image yet. Upload an image and click Process.
                          </Box>
                        )}
                      </div>
                    </Container>
                  </Grid>

                  <Container header={<Header variant="h2">Processing Information</Header>}>
                    <Box
                      padding={{ vertical: 's', horizontal: 'm' }}
                      style={{
                        minHeight: '400px',
                        maxHeight: '500px',
                        overflowY: 'auto',
                      }}
                    >
                      <div
                        style={{
                          fontSize: '14px',
                          lineHeight: '1.6',
                          color: '#2c3e50',
                          margin: 0,
                          wordBreak: 'break-word',
                        }}
                      >
                        {renderFormattedText(removeTimestamps(infoText) || 'Waiting for image processing...\n\nUpload an image and click "Process Image" to begin.')}
                      </div>
                    </Box>
                  </Container>

                  <ExpandableSection
                    headerText="Tips"
                    variant="container"
                    defaultExpanded={false}
                  >
                    <SpaceBetween size="s">
                      <Box variant="h4">Getting Started:</Box>
                      <Box>• Upload your image using the upload area above</Box>
                      <Box>• Select a detection method and adjust parameters as needed</Box>
                      <Box>• Click "Process Image" to see results</Box>

                      <Box variant="h4">Detection Methods:</Box>
                      <Box>• <strong>RF-DETR</strong> (recommended): Roboflow DETR, highly accurate detection</Box>
                      <Box>• <strong>RT-DETR</strong>: Real-time DETR, faster with similar accuracy to DETR</Box>
                      <Box>• <strong>DETR</strong>: State-of-the-art transformer-based detection</Box>
                      <Box>• <strong>YOLO</strong>: Fast and accurate for common objects</Box>
                      <Box>• <strong>Contour</strong>: Fast, works well with clear backgrounds</Box>
                      <Box>• <strong>Saliency</strong>: Identifies visually interesting regions</Box>
                      <Box>• <strong>Edge</strong>: Fast edge detection with Canny algorithm</Box>
                      <Box>• <strong>GrabCut</strong>: Precise foreground/background segmentation</Box>

                      <Box variant="h4">Aspect Ratio Options:</Box>
                      <Box>• <strong>None</strong>: Use the detected object bounds as-is</Box>
                      <Box>• <strong>Original</strong>: Maintain the original image's aspect ratio</Box>
                      <Box>• <strong>Custom</strong>: Specify your own ratio (e.g., 16:9, 4:3, 1.5, 2.35:1)</Box>

                      <Box variant="p" fontSize="body-s" color="text-status-info">
                        For RF-DETR/RT-DETR/DETR/YOLO, you can specify objects like: person, car, couch, chair, dog, cat, etc.
                      </Box>
                    </SpaceBetween>
                  </ExpandableSection>
                </SpaceBetween>
              </Grid>

              <Box textAlign="center" padding={{ top: 'l', bottom: 's' }}>
                <Box variant="small" color="text-status-inactive">
                  Gary A. Stafford, 2025
                </Box>
              </Box>
            </SpaceBetween>
          </ContentLayout>
        }
      />

      {/* Image Modal */}
      <Modal
        onDismiss={() => setModalVisible(false)}
        visible={modalVisible}
        size="max"
        header={modalImageTitle}
      >
        <Box textAlign="center">
          <img
            src={modalImageUrl}
            alt={modalImageTitle}
            style={{
              maxWidth: '100%',
              maxHeight: '80vh',
              height: 'auto',
              objectFit: 'contain',
            }}
          />
        </Box>
      </Modal>
    </>
  )
}

export default App
