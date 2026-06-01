import Foundation
import Vision
import ImageIO

func loadCGImage(path: String) -> CGImage? {
    let url = URL(fileURLWithPath: path)
    guard let source = CGImageSourceCreateWithURL(url as CFURL, nil) else { return nil }
    return CGImageSourceCreateImageAtIndex(source, 0, nil)
}

let args = Array(CommandLine.arguments.dropFirst())
guard !args.isEmpty else {
    fputs("usage: swift scripts/ocr_vision.swift IMAGE...\n", stderr)
    exit(2)
}

let encoder = JSONEncoder()
encoder.outputFormatting = [.withoutEscapingSlashes]

for path in args {
    autoreleasepool {
        guard let image = loadCGImage(path: path) else {
            let row: [String: Any] = ["path": path, "error": "cannot_load_image"]
            if let data = try? JSONSerialization.data(withJSONObject: row) {
                print(String(data: data, encoding: .utf8)!)
            }
            return
        }

        let request = VNRecognizeTextRequest()
        request.recognitionLevel = .accurate
        request.usesLanguageCorrection = false
        request.recognitionLanguages = ["zh-Hans", "en-US"]

        let handler = VNImageRequestHandler(cgImage: image, options: [:])
        do {
            try handler.perform([request])
            let observations = (request.results ?? []).compactMap { obs -> [String: Any]? in
                guard let candidate = obs.topCandidates(1).first else { return nil }
                let box = obs.boundingBox
                return [
                    "text": candidate.string,
                    "confidence": candidate.confidence,
                    "bbox": [
                        "x": box.origin.x,
                        "y": box.origin.y,
                        "w": box.size.width,
                        "h": box.size.height,
                    ],
                ]
            }
            let row: [String: Any] = [
                "path": path,
                "width": image.width,
                "height": image.height,
                "observations": observations,
            ]
            let data = try JSONSerialization.data(withJSONObject: row)
            print(String(data: data, encoding: .utf8)!)
        } catch {
            let row: [String: Any] = ["path": path, "error": String(describing: error)]
            if let data = try? JSONSerialization.data(withJSONObject: row) {
                print(String(data: data, encoding: .utf8)!)
            }
        }
    }
}
