namespace TeachingSkills.TriangleTrigQuestionBank

open System

type ExactValue = {
    Coefficient: string
    Radicand: int
    Latex: string
}

type AngleKind =
    | Acute
    | Right
    | Obtuse

type TrigFunction =
    | Sin
    | Cos
    | Tan
    | Cot

type TrigValues = {
    Sin: ExactValue
    Cos: ExactValue
    Tan: ExactValue option
    Cot: ExactValue option
}

type InternalAngle = {
    Kind: AngleKind
    Actual: TrigValues
    Reference: TrigValues
}

type AssignmentAngleRatio =
    | AcuteRatio of AngleName: string * Function: TrigFunction * Value: ExactValue
    | SupplementRatio of ObtuseAngleName: string * Function: TrigFunction * Value: ExactValue
    | RightAngleRatio of AngleName: string * Function: TrigFunction * Value: ExactValue

type TrigRatioEntry = {
    Id: string
    Ratios: TrigValues
    SourceNumberEntryIds: string list
}

type TrigRatioDatabaseSnapshot = private TrigRatioDatabaseSnapshot of TrigRatioEntry list

type TriangleShape = {
    Id: string
    Sides: Map<string, ExactValue>
    Angles: Map<string, InternalAngle>
    SourceTrigRatioIds: string list
    GeneratorVersion: string
}

type SsaCase = {
    Id: string
    KnownAngleName: string
    KnownAngle: InternalAngle
    OppositeSideName: string
    OppositeSide: ExactValue
    OtherKnownSideName: string
    OtherKnownSide: ExactValue
    MissingSideName: string
    TriangleIds: string list
    MissingSideAnswers: ExactValue list
}

type TriangleDatabaseSnapshot = private TriangleDatabaseSnapshot of TriangleShape list * SsaCase list

type ProblemType =
    | SSS
    | SAS
    | SSA
    | AAS
    | ASA

type ProblemTarget =
    | FindSide of SideName: string
    | FindTrigRatio of AngleName: string * Function: TrigFunction

type ProblemFact =
    | KnownSide of SideName: string * Value: ExactValue
    | KnownAngleRatio of AssignmentAngleRatio

type ProblemSpecification = {
    ProblemType: ProblemType
    Facts: ProblemFact list
    Target: ProblemTarget
}

type SolvedBranch = {
    TriangleId: string
    TargetValue: ExactValue
}

type SsaSolveResult =
    | NoSsaSolution
    | OneSsaSolution of SolvedBranch
    | TwoSsaSolutions of First: SolvedBranch * Second: SolvedBranch

type FinalAnswer =
    | OneValue of ExactValue
    | MultipleValues of ExactValue list

type AuditEvidence = {
    SolutionCount: int
    ReconstructedTriangleIds: string list
    GivensReproduced: bool
    AnswersVerified: bool
    PrintableValuesOnly: bool
    NoObtuseTrigInAssignment: bool
}

type CandidateQuestion = {
    Id: string
    ProblemType: ProblemType
    Specification: ProblemSpecification
    StemLatex: string
    Answer: FinalAnswer
    SourceTriangleIds: string list
    Audit: AuditEvidence
    ContentHash: string
}

type ReviewDecision =
    | Approve
    | Reject of Reason: string

type ApprovedQuestion = private ApprovedQuestion of CandidateQuestion

type BankMetadata = {
    Id: string
    Topic: string
    Grade: string
    Version: string
    CreatedAt: DateTimeOffset
}

type QuestionBankSnapshot = private QuestionBankSnapshot of BankMetadata * ApprovedQuestion list

type SamplingRequest = {
    CountsByType: Map<ProblemType, int>
    ExcludeItemIds: Set<string>
    Seed: int64
}

type CoverageShortage = {
    ProblemType: ProblemType
    Requested: int
    Available: int
}

type SamplingFailure =
    | InvalidSamplingRequest of string list
    | InsufficientQuestions of CoverageShortage list
    | BankUnavailable

type SampledItem = {
    ItemId: string
    ProblemType: ProblemType
}

type SamplingReceipt = {
    BankId: string
    BankVersion: string
    Seed: int64
    SelectedItems: SampledItem list
}

type AssignmentQuestion = {
    Id: string
    StemLatex: string
    AnswerLatex: string
}

type AssignmentPackage = {
    Title: string
    Questions: AssignmentQuestion list
    Receipt: SamplingReceipt
}

type BuildError = {
    Code: string
    Message: string
    SourceId: string option
}

type ReviewError =
    | StaleCandidateHash
    | InvalidCandidate of string list

type PublishError =
    | NoApprovedQuestions
    | DuplicateQuestionIds of string list

type AssemblyError =
    | ReceiptDoesNotMatchBank
    | MissingSampledItems of string list
    | AssignmentValidationFailed of string list

type ReviewedNumberSource =
    abstract LoadAvailableRightTriangles:
        unit -> Async<Result<string, string>>

type QuestionBankStore =
    abstract SaveSnapshot:
        QuestionBankSnapshot -> Async<Result<unit, string>>

    abstract LoadSnapshot:
        BankId: string * Version: string option
            -> Async<Result<QuestionBankSnapshot, string>>

type AssignmentWriter =
    abstract Write:
        OutputPath: string * Package: AssignmentPackage
            -> Async<Result<string, string>>

module AngleCatalog =
    let build (_: ReviewedNumberSource) : Async<Result<TrigRatioDatabaseSnapshot, BuildError list>> =
        async { return Error [] }

module TriangleShapeLibrary =
    let build (_: TrigRatioDatabaseSnapshot) : Result<TriangleDatabaseSnapshot, BuildError list> =
        Error []

module ProblemGeneration =
    let generate (_: TriangleDatabaseSnapshot) : CandidateQuestion list =
        []

module SsaSolver =
    let solve (_: ProblemSpecification) =
        NoSsaSolution

module QuestionAudit =
    let audit (candidate: CandidateQuestion) : Result<CandidateQuestion, BuildError list> =
        Ok candidate

module ReviewWorkflow =
    let decide ExpectedContentHash decision candidate =
        if ExpectedContentHash <> candidate.ContentHash then
            Error StaleCandidateHash
        else
            match decision with
            | Approve -> Ok (Some (ApprovedQuestion candidate))
            | Reject _ -> Ok None

module QuestionBank =
    let publish metadata questions =
        match questions with
        | [] -> Error NoApprovedQuestions
        | values -> Ok (QuestionBankSnapshot (metadata, values))

module BankSampler =
    let sample (_: QuestionBankSnapshot) (_: SamplingRequest) : Result<SamplingReceipt, SamplingFailure> =
        Error BankUnavailable

module AssignmentAssembler =
    let assemble (_: QuestionBankSnapshot) (_: SamplingReceipt) : Result<AssignmentPackage, AssemblyError> =
        Error ReceiptDoesNotMatchBank
