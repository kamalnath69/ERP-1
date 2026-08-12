from app.models.base import Base, TimestampMixin, TenantMixin, uuid_pk
from app.models.organization import (
    IndustryEnum, IndustryMigrationRequest, Location, Organization,
    OrganizationStatusEnum, SubscriptionPlanEnum,
)
from app.models.user import (
    AuthAttempt, AuthCode, RefreshToken, User, UserMFADevice, UserPreference,
    UserRecoveryCode,
)
from app.models.role import AccessScope, Permission, Role, RolePermission, UserPermissionOverride, UserRole
from app.models.business import (
    Appointment, CatalogItem, Category, Client, Employee, EmployeeLocation, SaleInvoice,
    SaleLine, SalePayment, StaffSchedule, StockLevel, StockMovement, Task,
)
from app.models.gym import (
    ClassBooking, DietPlan, Equipment, FitnessMeasurement, GymCheckIn, GymClass,
    Membership, MembershipPlan, TrainerAssignment, WorkoutPlan,
)
from app.models.clinic import (
    Allergy, Diagnosis, Dispense, Encounter, LabOrder, LabResult, LabTest, PatientProfile,
    Prescription, PrescriptionItem, Vital,
)
from app.models.college import (
    CollegeAssessment, CollegeAssessmentScore, CollegeAttendanceRecord,
    CollegeAttendanceSession, CollegeCohort, CollegeCourse, CollegeCourseOffering,
    CollegeDepartment, CollegeFeePlan, CollegeProgram, CollegeStudentFee,
    CollegeStudentProfile, CollegeTerm,
)
from app.models.college_placement import (
    CollegeApplicationStageEvent, CollegeAttendanceSnapshot, CollegeCareerEvidence,
    CollegeCareerProfile, CollegeCodingAccount, CollegeCodingSnapshot,
    CollegeClearanceSnapshot, CollegeDataConnector, CollegeExternalRecord, CollegeImportRun,
    CollegeIntegrationCredential, CollegeIntegrationRateBucket,
    CollegePipelineStage, CollegePlacementApplication, CollegePlacementAssessment,
    CollegePlacementCompany, CollegePlacementInterview, CollegePlacementOffer,
    CollegePlacementOpportunity, CollegePreparationActivity, CollegeReadinessPolicy,
    CollegeReadinessSnapshot, CollegeResumeDraft, CollegeStudentIntervention,
    CollegeTermResult,
)
from app.models.documents import Document, DocumentChunk, Job, OutboundMessage
from app.models.ai import (
    AIAction, AIIntentResolution, AIMessageFeedback, AIResultSession, AISavedView, AIUsage,
    ChatConversation, ChatMessage, ChatTurn,
)
from app.models.audit import AuditLog
from app.models.public_site import DemoRequest, LegalAcceptance, LegalDocument
from app.models.billing import (
    BillingCheckoutAttempt, Invoice, PaymentEvent, ProviderPlanMapping,
    Subscription, SubscriptionSchedule,
)
from app.models.settings import FeatureFlag, Notification, Setting
from app.models.client_intelligence import (
    ClientCommitment, ClientMemory, ClientSignal, CoachingNote, ClientMedia,
    FitnessGoal, SalonClientProfile, WorkoutSession,
)
from app.models.platform import (
    AIWallet, ApprovalRequest, BillingProfile, FeatureDefinition, OrganizationDeletionRequest,
    OrganizationEntitlementOverride, PlanDefinition, PlanEntitlement, PlanVersion,
    PlatformMFADevice, PlatformPayment, PlatformPermission, PlatformRecoveryCode,
    PlatformRefund, PlatformRole, PlatformRolePermission, PlatformSetting, PlatformSettlement,
    PlatformUserRole, RechargePack, RetentionArchive, SignupCheckout, SupportSession, WalletLedger,
    WalletCreditGrant, WalletReservation,
)

__all__ = [name for name in globals() if not name.startswith("_")]
