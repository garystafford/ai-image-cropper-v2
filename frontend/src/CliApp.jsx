import { useState } from 'react'
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
  FileUpload,
  Alert,
  Box,
  ExpandableSection,
  Toggle,
  Textarea,
  TokenGroup,
} from '@cloudscape-design/components'
import axios from 'axios'

const API_BASE_URL = ''

function CliApp() {
  // State for CLI form inputs
  const [imageFiles, setImageFiles] = useState([]) // Changed to support multiple files
  const [method, setMethod] = useState({ value: 'rf-detr', label: 'RF-DETR' })
  const [objectNames, setObjectNames] = useState([]) // Array of objects
  const [objectInput, setObjectInput] = useState('') // Current input value
  const [confidence, setConfidence] = useState(0.7)
  const [keepAspect, setKeepAspect] = useState(false)
  const [customAspect, setCustomAspect] = useState('')
  const [padding, setPadding] = useState(0)
  const [threshold, setThreshold] = useState(240)
  const [batchCrop, setBatchCrop] = useState(false)
  const [batchOutputDir, setBatchOutputDir] = useState('cropped_images')
  const [visualize, setVisualize] = useState(true)
  const [debugMode, setDebugMode] = useState(false)
  const [cropOutputPath, setCropOutputPath] = useState('')
  const [visOutputPath, setVisOutputPath] = useState('')

  // State for results
  const [isProcessing, setIsProcessing] = useState(false)
  const [errorMessage, setErrorMessage] = useState('')
  const [processedResults, setProcessedResults] = useState([]) // Array of results for multiple images
  const [currentProcessing, setCurrentProcessing] = useState(0) // Track progress
  const [totalToProcess, setTotalToProcess] = useState(0)

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

  // Handle adding an object to the list
  const handleAddObject = () => {
    if (objectInput.trim()) {
      setObjectNames([...objectNames, { label: objectInput.trim(), value: objectInput.trim() }])
      setObjectInput('')
    }
  }

  // Handle removing an object from the list
  const handleRemoveObject = (index) => {
    setObjectNames(objectNames.filter((_, i) => i !== index))
  }

  // Generate equivalent CLI command
  const generateCliCommand = (filename) => {
    let command = `python cropper.py "${filename}"`
    
    // Add method
    if (method.value !== 'contour') {
      command += ` --method ${method.value}`
    }
    
    // Add objects
    objectNames.forEach(obj => {
      command += ` --object "${obj.value}"`
    })
    
    // Add confidence if not default
    if (confidence !== 0.7) {
      command += ` --confidence ${confidence}`
    }
    
    // Add aspect ratio options
    if (keepAspect) {
      command += ` --keep-aspect`
    } else if (customAspect.trim()) {
      command += ` --aspect-ratio "${customAspect}"`
    }
    
    // Add padding if not zero
    if (padding > 0) {
      command += ` --padding ${padding}`
    }
    
    // Add threshold if not default for contour method
    if (method.value === 'contour' && threshold !== 240) {
      command += ` --threshold ${threshold}`
    }
    
    // Add batch crop
    if (batchCrop) {
      command += ` --batch-crop`
      if (batchOutputDir !== 'cropped_images') {
        command += ` --batch-output-dir "${batchOutputDir}"`
      }
    }
    
    // Add visualization
    if (visualize) {
      command += ` --visualize`
    }
    
    // Add debug mode
    if (debugMode) {
      command += ` --debug`
    }
    
    // Add output paths
    if (cropOutputPath.trim()) {
      command += ` --crop-output "${cropOutputPath}"`
    }
    
    if (visOutputPath.trim()) {
      command += ` --vis-output "${visOutputPath}"`
    }
    
    return command
  }

  const handleProcessCli = async () => {
    if (imageFiles.length === 0) {
      setErrorMessage('Please upload at least one image.')
      return
    }

    // Validate file types before processing
    const validExtensions = ['.jpg', '.jpeg', '.png', '.webp']
    const validMimeTypes = ['image/jpeg', 'image/png', 'image/webp']
    const invalidFiles = imageFiles.filter(file => {
      const extension = file.name.toLowerCase().substring(file.name.lastIndexOf('.'))
      return !validExtensions.includes(extension) && !validMimeTypes.includes(file.type)
    })

    if (invalidFiles.length > 0) {
      setErrorMessage(`Invalid file type(s) detected: ${invalidFiles.map(f => f.name).join(', ')}. Only JPEG, PNG, and WebP are supported.`)
      return
    }

    setIsProcessing(true)
    setErrorMessage('')
    setProcessedResults([])
    setCurrentProcessing(0)
    setTotalToProcess(imageFiles.length)

    const results = []

    // Process each image sequentially
    for (let i = 0; i < imageFiles.length; i++) {
      setCurrentProcessing(i + 1)
      const file = imageFiles[i]

      const formData = new FormData()
      formData.append('file', file)
      formData.append('method', method.value)

      // Add all target objects
      objectNames.forEach(obj => {
        formData.append('object', obj.value)
      })

      formData.append('confidence', confidence)
      formData.append('keep_aspect', keepAspect)
      formData.append('aspect_ratio', customAspect)
      formData.append('padding', padding)
      formData.append('threshold', threshold)
      formData.append('batch_crop', batchCrop)
      formData.append('batch_output_dir', batchOutputDir)
      formData.append('visualize', visualize)
      formData.append('debug', debugMode)
      formData.append('crop_output', cropOutputPath)
      formData.append('vis_output', visOutputPath)

      try {
        const response = await axios.post(`${API_BASE_URL}/api/cli-process`, formData, {
          headers: {
            'Content-Type': 'multipart/form-data',
          },
        })

        const data = response.data
        const timestamp = new Date().getTime()

        // Build result object for this image
        const result = {
          filename: file.name,
          success: true,
          output: data.output || 'Processing complete!',
          cliCommand: generateCliCommand(file.name),
          images: [],
          batchFiles: data.batch_files || []
        }

        if (data.visualization_url) {
          result.images.push({
            url: `${API_BASE_URL}${data.visualization_url}?t=${timestamp}`,
            title: 'Visualization'
          })
        }
        if (data.cropped_url) {
          result.images.push({
            url: `${API_BASE_URL}${data.cropped_url}?t=${timestamp}`,
            title: 'Cropped Image'
          })
        }

        results.push(result)
      } catch (error) {
        // Add error result for this image
        results.push({
          filename: file.name,
          success: false,
          output: error.response?.data?.output || '',
          error: error.response?.data?.detail || 'Error processing image',
          cliCommand: generateCliCommand(file.name),
          images: [],
          batchFiles: []
        })
        console.error(`Error processing ${file.name}:`, error)
      }
    }

    setProcessedResults(results)
    setIsProcessing(false)
    setCurrentProcessing(0)
    setTotalToProcess(0)

    // Show summary message
    const successCount = results.filter(r => r.success).length
    const failCount = results.filter(r => !r.success).length
    if (failCount > 0) {
      setErrorMessage(`Processed ${successCount} images successfully, ${failCount} failed.`)
    }
  }

  return (
    <AppLayout
      navigationHide
      toolsHide
      content={
        <ContentLayout
          header={
            <SpaceBetween size="m">
              <Header variant="h1">
                Batch Processing
              </Header>
              <Box variant="p">
                Process single or multiple images with advanced configuration options.
                Upload multiple images at once for batch processing with full control over all detection and cropping parameters.
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
              {/* Left Column - CLI Parameters */}
              <SpaceBetween size="l">
                <Container header={<Header variant="h2">Image Input</Header>}>
                  <FormField
                    label="Upload Images"
                    description="Select one or more images to process. To upload from a directory: click 'Choose files', navigate to your folder, then select all files (Ctrl+A or Cmd+A)"
                  >
                    <FileUpload
                      onChange={({ detail }) => setImageFiles(detail.value)}
                      value={imageFiles}
                      multiple
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
                      tokenLimit={10}
                      constraintText="Supported formats: JPEG, PNG, WebP. Tip: Use Ctrl+A (or Cmd+A on Mac) to select all files in a folder."
                    />
                  </FormField>
                  {imageFiles.length > 0 && (
                    <Box variant="awsui-key-label" margin={{ top: 's' }}>
                      {imageFiles.length} image(s) selected
                    </Box>
                  )}
                </Container>

                <Container header={<Header variant="h2">Detection Options</Header>}>
                  <SpaceBetween size="l">
                    <FormField
                      label="Detection Method"
                      description="Choose the algorithm for object detection"
                    >
                      <Select
                        selectedOption={method}
                        onChange={({ detail }) => setMethod(detail.selectedOption)}
                        options={detectionMethods}
                      />
                    </FormField>

                    <FormField
                      label="Target Objects (optional)"
                      description="Specify objects to detect (e.g., couch, person, chair). Works with YOLO/DETR methods only."
                    >
                      <SpaceBetween size="xs">
                        <div style={{ display: 'flex', gap: '8px' }}>
                          <div style={{ flex: 1 }}>
                            <Input
                              value={objectInput}
                              onChange={({ detail }) => setObjectInput(detail.value)}
                              placeholder="e.g., couch, person, chair"
                              onKeyDown={(e) => {
                                if (e.detail.key === 'Enter') {
                                  handleAddObject()
                                }
                              }}
                            />
                          </div>
                          <Button onClick={handleAddObject} disabled={!objectInput.trim()}>
                            Add
                          </Button>
                        </div>
                        {objectNames.length > 0 && (
                          <TokenGroup
                            items={objectNames.map((obj, index) => ({
                              label: obj.label,
                              dismissLabel: `Remove ${obj.label}`,
                            }))}
                            onDismiss={({ detail }) => handleRemoveObject(detail.itemIndex)}
                          />
                        )}
                      </SpaceBetween>
                    </FormField>

                    <FormField
                      label="Confidence Threshold"
                      description="Minimum confidence for YOLO/DETR detections (0-1)"
                    >
                      <Slider
                        onChange={({ detail }) => setConfidence(detail.value)}
                        value={confidence}
                        min={0.1}
                        max={1.0}
                        step={0.05}
                        valueFormatter={value => value.toFixed(2)}
                      />
                    </FormField>

                    <FormField
                      label="Binary Threshold"
                      description="Threshold for contour detection method (0-255)"
                    >
                      <Slider
                        onChange={({ detail }) => setThreshold(detail.value)}
                        value={threshold}
                        min={0}
                        max={255}
                        step={5}
                      />
                    </FormField>
                  </SpaceBetween>
                </Container>

                <Container header={<Header variant="h2">Crop Options</Header>}>
                  <SpaceBetween size="l">
                    <FormField label="Aspect Ratio">
                      <SpaceBetween size="s">
                        <Toggle
                          checked={keepAspect}
                          onChange={({ detail }) => {
                            setKeepAspect(detail.checked)
                            if (detail.checked) setCustomAspect('')
                          }}
                        >
                          Keep original aspect ratio
                        </Toggle>

                        <FormField
                          label="Custom Aspect Ratio"
                          description="Enter ratio as width:height (16:9) or decimal (1.78)"
                        >
                          <Input
                            value={customAspect}
                            onChange={({ detail }) => {
                              setCustomAspect(detail.value)
                              if (detail.value) setKeepAspect(false)
                            }}
                            placeholder="e.g., 16:9, 4:3, 1.5, or 2.35"
                            disabled={keepAspect}
                          />
                        </FormField>
                      </SpaceBetween>
                    </FormField>

                    <FormField
                      label="Padding (%)"
                      description="Add padding around the detected object (0-50%)"
                    >
                      <Slider
                        onChange={({ detail }) => setPadding(detail.value)}
                        value={padding}
                        min={0}
                        max={50}
                        step={1}
                      />
                    </FormField>
                  </SpaceBetween>
                </Container>

                <Container header={<Header variant="h2">Output Options</Header>}>
                  <SpaceBetween size="l">
                    <FormField label="Batch Crop Mode">
                      <Toggle
                        checked={batchCrop}
                        onChange={({ detail }) => setBatchCrop(detail.checked)}
                      >
                        Crop all detected objects individually (YOLO/DETR only)
                      </Toggle>
                    </FormField>

                    {batchCrop && (
                      <FormField
                        label="Batch Output Directory"
                        description="Directory to save batch cropped images"
                      >
                        <Input
                          value={batchOutputDir}
                          onChange={({ detail }) => setBatchOutputDir(detail.value)}
                          placeholder="cropped_images"
                        />
                      </FormField>
                    )}

                    <FormField
                      label="Crop Output Path"
                      description="Path to save the cropped image (optional)"
                    >
                      <Input
                        value={cropOutputPath}
                        onChange={({ detail }) => setCropOutputPath(detail.value)}
                        placeholder="e.g., output/cropped.jpg"
                      />
                    </FormField>

                    <FormField
                      label="Visualization Output Path"
                      description="Path to save the visualization image (optional)"
                    >
                      <Input
                        value={visOutputPath}
                        onChange={({ detail }) => setVisOutputPath(detail.value)}
                        placeholder="e.g., output/visualization.jpg"
                      />
                    </FormField>

                    <FormField label="Visualization Options">
                      <SpaceBetween size="s">
                        <Toggle
                          checked={visualize}
                          onChange={({ detail }) => setVisualize(detail.checked)}
                        >
                          Generate visualization
                        </Toggle>

                        <Toggle
                          checked={debugMode}
                          onChange={({ detail }) => setDebugMode(detail.checked)}
                        >
                          Debug mode (save intermediate images)
                        </Toggle>
                      </SpaceBetween>
                    </FormField>

                    <Button
                      variant="primary"
                      onClick={handleProcessCli}
                      loading={isProcessing}
                      fullWidth
                      iconName="upload"
                    >
                      {isProcessing && totalToProcess > 0
                        ? `Processing ${currentProcessing} of ${totalToProcess}...`
                        : imageFiles.length > 1
                        ? `Process ${imageFiles.length} Images`
                        : 'Process Image'}
                    </Button>
                  </SpaceBetween>
                </Container>
              </SpaceBetween>

              {/* Right Column - Results */}
              <SpaceBetween size="l">
                {processedResults.length === 0 ? (
                  <Container header={<Header variant="h2">Processing Output</Header>}>
                    <Box
                      padding={{ vertical: 's', horizontal: 'm' }}
                      className="processing-output-container"
                      style={{
                        minHeight: '300px',
                        maxHeight: '500px',
                        overflowY: 'auto',
                      }}
                    >
                      <pre className="processing-output-text">
                        Processing output will appear here after processing...{'\n\n'}Upload one or more images and configure parameters to begin.{'\n\n'}💡 Tip: You can upload multiple images at once for batch processing!
                      </pre>
                    </Box>
                  </Container>
                ) : (
                  <>
                    {/* Summary */}
                    <Container>
                      <SpaceBetween size="s">
                        <Box variant="h2">Processing Summary</Box>
                        <Box>
                          <strong>Total images processed:</strong> {processedResults.length}
                        </Box>
                        <Box>
                          <strong>Successful:</strong> {processedResults.filter(r => r.success).length} |
                          <strong> Failed:</strong> {processedResults.filter(r => !r.success).length}
                        </Box>
                      </SpaceBetween>
                    </Container>

                    {/* Individual Results */}
                    {processedResults.map((result, idx) => (
                      <Container
                        key={idx}
                        header={
                          <Header
                            variant="h2"
                            actions={
                              result.success ? (
                                <Box color="text-status-success">✓ Success</Box>
                              ) : (
                                <Box color="text-status-error">✗ Failed</Box>
                              )
                            }
                          >
                            {result.filename}
                          </Header>
                        }
                      >
                        <SpaceBetween size="l">
                          {/* Processing Output */}
                          <ExpandableSection
                            headerText="Processing Output"
                            variant="default"
                            defaultExpanded={processedResults.length === 1}
                          >
                            <Box
                              padding={{ vertical: 's', horizontal: 'm' }}
                              className="processing-output-container"
                              style={{
                                maxHeight: '400px',
                                overflowY: 'auto',
                              }}
                            >
                              <pre className="result-output-text">
                                {result.output || 'No output available'}
                              </pre>
                            </Box>
                          </ExpandableSection>

                          {/* Equivalent CLI Command */}
                          <ExpandableSection
                            headerText="Equivalent CLI Command"
                            variant="default"
                            defaultExpanded={false}
                          >
                            <Box
                              padding={{ vertical: 's', horizontal: 'm' }}
                              style={{
                                backgroundColor: '#f8f9fa',
                                borderRadius: '4px',
                              }}
                            >
                              <SpaceBetween size="s">
                                <Box variant="small" color="text-status-info">
                                  You can run this equivalent command in the terminal:
                                </Box>
                                <Box
                                  padding={{ vertical: 'xs', horizontal: 's' }}
                                  className="cli-command-container"
                                  style={{
                                    backgroundColor: '#232f3e',
                                    borderRadius: '4px',
                                    border: '1px solid #414d5c',
                                  }}
                                >
                                  <pre
                                    className="cli-command-text"
                                    style={{
                                      fontSize: '12px',
                                      lineHeight: '1.5',
                                      margin: 0,
                                      whiteSpace: 'pre-wrap',
                                      wordBreak: 'break-all',
                                      fontFamily: 'Monaco, Menlo, "Ubuntu Mono", Consolas, monospace',
                                    }}
                                  >
                                    {result.cliCommand}
                                  </pre>
                                </Box>
                                <Button
                                  size="small"
                                  iconName="copy"
                                  onClick={() => {
                                    navigator.clipboard.writeText(result.cliCommand)
                                  }}
                                >
                                  Copy Command
                                </Button>
                              </SpaceBetween>
                            </Box>
                          </ExpandableSection>

                          {/* Error Message */}
                          {!result.success && result.error && (
                            <Alert type="error">
                              {result.error}
                            </Alert>
                          )}

                          {/* Result Images */}
                          {result.images.length > 0 && (
                            <Grid gridDefinition={result.images.length === 1 ? [{ colspan: 12 }] : [{ colspan: 6 }, { colspan: 6 }]}>
                              {result.images.map((img, imgIdx) => (
                                <Box key={imgIdx} textAlign="center">
                                  <SpaceBetween size="s">
                                    <Box variant="h4">{img.title}</Box>
                                    <img
                                      src={img.url}
                                      alt={img.title}
                                      style={{
                                        maxWidth: '100%',
                                        maxHeight: '400px',
                                        width: 'auto',
                                        height: 'auto',
                                        borderRadius: '4px',
                                        border: '1px solid #d5dbdb',
                                        objectFit: 'contain',
                                      }}
                                    />
                                  </SpaceBetween>
                                </Box>
                              ))}
                            </Grid>
                          )}

                          {/* Batch Files */}
                          {result.batchFiles.length > 0 && (
                            <Box>
                              <SpaceBetween size="s">
                                <Box variant="h4">
                                  Batch Cropped Objects ({result.batchFiles.length})
                                </Box>
                                <Grid gridDefinition={[{ colspan: 6 }, { colspan: 6 }]}>
                                  {result.batchFiles.map((file, fileIdx) => (
                                    <Button
                                      key={fileIdx}
                                      href={`${API_BASE_URL}${file}`}
                                      target="_blank"
                                      iconName="download"
                                      fullWidth
                                    >
                                      {file.split('/').pop()}
                                    </Button>
                                  ))}
                                </Grid>
                              </SpaceBetween>
                            </Box>
                          )}
                        </SpaceBetween>
                      </Container>
                    ))}
                  </>
                )}

                <ExpandableSection
                  headerText="CLI Command Reference"
                  variant="container"
                  defaultExpanded={false}
                >
                  <SpaceBetween size="s">
                    <Box variant="h4">Detection Methods:</Box>
                    <Box>• <strong>rf-detr</strong> (recommended): Roboflow DETR, highly accurate detection (requires rfdetr)</Box>
                    <Box>• <strong>rt-detr</strong>: Real-time DETR, faster with similar accuracy (requires transformers + torch)</Box>
                    <Box>• <strong>detr</strong>: State-of-the-art transformer-based detection (requires transformers + torch)</Box>
                    <Box>• <strong>yolo</strong>: Fast and accurate deep learning (requires ultralytics)</Box>
                    <Box>• <strong>contour</strong>: Fast, works well with clear backgrounds</Box>
                    <Box>• <strong>saliency</strong>: Identifies visually interesting regions</Box>
                    <Box>• <strong>edge</strong>: Fast edge detection using Canny algorithm</Box>
                    <Box>• <strong>grabcut</strong>: Foreground/background segmentation</Box>

                    <Box variant="h4">Example CLI Commands:</Box>
                    <Box>
                      <pre className="example-code-block">
{`# Basic usage
python cropper.py image.jpg --visualize --crop-output output.jpg

# RF-DETR with specific object
python cropper.py room.jpg --method rf-detr --object couch --aspect-ratio 16:9

# Batch crop all detected objects
python cropper.py family.jpg --method rf-detr --batch-crop --batch-output-dir ./people

# With padding and custom aspect ratio
python cropper.py photo.jpg --method rt-detr --padding 15 --aspect-ratio 4:3`}
                      </pre>
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
  )
}

export default CliApp
