namespace TeachingSkills.TriangleTrigQuestionBank

open System

/// An exact printable value q*sqrt(d).  Radicand is square-free; rational
/// values use Radicand = 1.  Audit code may use richer symbolic expressions,
/// but only values representable by this contract can be published.
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

/// Complete internal evidence.  It never crosses the assignment boundary.
type InternalAngle = {
    Kind: AngleKind
    Actual: TrigValues
    Reference: TrigValues
}

/// The only angle facts that an assignment is allowed to display.
/// There is deliberately no case for a trigonometric ratio of an obtuse angle.
type AssignmentAngleRatio =
    | AcuteRatio of AngleName: string * Function: TrigFunction * Value: ExactValue
    | SupplementRatio of ObtuseAngleName: string * Function: TrigFunction * Value: ExactValue
    | RightAngleRatio of AngleName: string * Function: TrigFunction * Value: ExactValue

/// Stage 1 materialization.  Entries are deduplicated acute angles derived
/// from reviewed right-triangle records in the training-number database.
type TrigRatioEntry = {
    Id: string
    Ratios: TrigValues
    SourceNumberEntryIds: string list
}

type TrigRatioDatabaseSnapshot

type TriangleShape = {
    Id: string
    Sides: Map<string, ExactValue>
    Angles: Map<string, InternalAngle>
    SourceTrigRatioIds: string list
    GeneratorVersion: string
}

/// An SSA equivalence class is part of the triangle library, not the question
/// generator.  TriangleIds contains exactly one or two already materialized
/// triangles sharing the same displayed SSA facts.
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

/// Stage 2 materialization.  This is the only input accepted by question
/// generation.
type TriangleDatabaseSnapshot

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

/// Published answers are non-empty and contain distinct, sorted values.
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

type ApprovedQuestion

type BankMetadata = {
    Id: string
    Topic: string
    Grade: string
    Version: string
    CreatedAt: DateTimeOffset
}

type QuestionBankSnapshot

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
    /// Stage 1: reviewed number database -> durable trigonometric-ratio database.
    val build:
        ReviewedNumberSource
            -> Async<Result<TrigRatioDatabaseSnapshot, BuildError list>>

module TriangleShapeLibrary =
    /// Stage 2: trigonometric-ratio database -> durable triangle database.
    val build:
        TrigRatioDatabaseSnapshot
            -> Result<TriangleDatabaseSnapshot, BuildError list>

module ProblemGeneration =
    /// Stage 3: triangle database -> candidate question bank.  This operation
    /// has no number-database or trigonometric-database input.
    val generate:
        TriangleDatabaseSnapshot
            -> CandidateQuestion list

module SsaSolver =
    val solve:
        ProblemSpecification
            -> SsaSolveResult

module QuestionAudit =
    val audit:
        CandidateQuestion
            -> Result<CandidateQuestion, BuildError list>

module ReviewWorkflow =
    val decide:
        ExpectedContentHash: string
        -> ReviewDecision
        -> CandidateQuestion
        -> Result<ApprovedQuestion option, ReviewError>

module QuestionBank =
    val publish:
        BankMetadata
        -> ApprovedQuestion list
        -> Result<QuestionBankSnapshot, PublishError>

module BankSampler =
    val sample:
        QuestionBankSnapshot
        -> SamplingRequest
        -> Result<SamplingReceipt, SamplingFailure>

module AssignmentAssembler =
    val assemble:
        QuestionBankSnapshot
        -> SamplingReceipt
        -> Result<AssignmentPackage, AssemblyError>
