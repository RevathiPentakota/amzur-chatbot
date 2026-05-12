using System.Dynamic;
using Newtonsoft.Json;

namespace ConsoleAppV6
{
    public class Program
    {
        public static void Main(string[] args)
        {
            string patientLastName, patientPhone, patientDOB, patientFirstName, PatientUUID, InsChoice;
            string? insurancePCN = null, insuranceGroupNumber = null, insuranceMemberID = null, insurancePlanName = null;
            Guid insuranceRxUUID;

            string userChoice;

            do
            {///this block is not needed for load process
                Console.Write("\nWhich type of prescription do you need: ");
                Console.Write("\n1. New");
                Console.Write("\n2. Old");
                Console.Write("\n3. Exit");
                Console.Write("\nEnter your choice: ");
                userChoice = Console.ReadLine().ToLower();

                dynamic patientPrescription = new ExpandoObject();

                switch (userChoice)
                {
                    case "1":
                        patientFirstName = GetRandomPatientFirstName();
                        patientLastName = GetRandomPatientLastName();
                        patientPhone = GetRandomPhoneNumber();
                        patientDOB = GetRandomDateOfBirth();
                        PatientUUID = Guid.NewGuid().ToString();

                        GetData(patientFirstName, patientLastName, patientDOB, PatientUUID, patientPhone);
                        break;
                    case "2":
                        Console.Write("\n\nEnter Patient First Name: ");
                        patientFirstName = Console.ReadLine();

                        Console.Write("\n\nEnter Patient Last Name: ");
                        patientLastName = Console.ReadLine();

                        Console.Write("\nEnter Patient Date of Birth (yyyy-mm-dd): ");
                        patientDOB = Console.ReadLine();

                        Console.Write("\nEnter Patient Phone Number: ");
                        patientPhone = Console.ReadLine();
                        if(string.IsNullOrWhiteSpace(patientPhone))
                            patientPhone = GetRandomPhoneNumber();

                        Console.Write("\nEnter Patient UUID: ");
                        PatientUUID = Console.ReadLine();
                        GetData(patientFirstName, patientLastName, patientDOB, PatientUUID, patientPhone);
                        break;
                    default:
                        Console.Write("\nInvalid Option, try again ");
                        break;
                }
            } while (userChoice != "3");
        }

        public static void GetData(string FirstName, string LastName,
                                    string DOB, string PatientUUID, string phone)
        {
            //Console.Write("\nDo you need Insurance Information (yes/no): ");
            //string InsChoice = Console.ReadLine().ToLower();

            dynamic patientPrescription = new ExpandoObject();
            var prescriptionDict = (IDictionary<string, object>)patientPrescription;

            var rxUUID = Guid.NewGuid();
            var pharmacyNPI = GetRandomNPI();
            var pharmacyDEA = GetRandomDEA();
            var pharmacyName = GetRandomPharmacyName();
            var pharmacyAddress1 = GetRandomAddress();
            var pharmacyAddress2 = GetRandomAddress();
            var pharmacyCity = GetRandomCity();
            var pharmacyState = GetRandomState();
            var pharmacyZip = GetRandomZip();
            var pharmacyPhone = GetRandomPhoneNumber();
            var pharmacyFax = GetRandomPhoneNumber();
            var pharmacyWebsite = GetRandomWebsite();
            var pharmacyDispenseMethod = GetRandomDispenseMethod();
            var pharmacyNCPDP = GetRandomNCPDP();

            var PrescriberNPI = GetRandomNPI();
            var PrescriberDEA = GetRandomDEA();
            var PrescriberName = GetRandomPrescriberName();
            var PrescriberAddress = GetRandomAddress();
            var PrescriberPhone = GetRandomPhoneNumber();
            var PrescriberCity = GetRandomCity();
            var PrescriberState = GetRandomState();
            var PrescriberZip = GetRandomZip();
            var PrescriberSpecialty = GetRandomSpecialty();
            var PrescriberOfficePhone = GetRandomPhoneNumber();
            var PrescriberFax = "14079006176";
            var PrescriberRxUUID = rxUUID;

            var rxId = GetRandomRxId();

            //prescriptionDict["PatientInfo.PatientUUId"] = PatientUUID;
            //prescriptionDict["PatientInfo.PatientFirstName"] = "Maeve";//FirstName;
            //prescriptionDict["PatientInfo.PatientLastName"] = "Breckenridge";//LastName;
            //prescriptionDict["PatientInfo.PatientDOB"] = "2000-01-01";//DOB;
            //prescriptionDict["PatientInfo.PatientGender"] = GetRandomGender();
            //prescriptionDict["PatientInfo.PatientPhone"] = "3035551212";//"4079006176";
            //prescriptionDict["PatientInfo.PatientAddress"] = "22 Main St";// GetRandomAddress();
            prescriptionDict["PatientInfo.PatientFirstName"] = FirstName;
            prescriptionDict["PatientInfo.PatientLastName"] = LastName;
            prescriptionDict["PatientInfo.PatientDOB"] = DOB;
            prescriptionDict["PatientInfo.PatientGender"] = GetRandomGender();
            prescriptionDict["PatientInfo.PatientPhone"] = GetRandomPhoneNumber();
            ;
            prescriptionDict["PatientInfo.PatientAddress"] = GetRandomAddress();
            prescriptionDict["PatientInfo.PatientSSN"] = GetRandomSSN();
            prescriptionDict["PatientInfo.PatientCity"] = GetRandomCity();

            //Console.Write("\nEnter Patient State (AZ/FL/CA): ");
            string PatientState = GetRandomState();

            prescriptionDict["PatientInfo.PatientState"] = PatientState;//GetRandomState();
            prescriptionDict["PatientInfo.PatientRxUUID"] = rxUUID;
            prescriptionDict["PatientInfo.PatientZip"] = "80013";//GetRandomZip();
            prescriptionDict["PatientInfo.Latitude"] = "27.9506";
            prescriptionDict["PatientInfo.Longitude"] = "-82.4572";

            //Console.Write("\nDo you want default EmployerConfigId to 2 (y - yes/n - No): ");
            //string deaultConfig = Console.ReadLine();

            //if (deaultConfig.ToLower() == "y")
            //    prescriptionDict["PatientInfo.EmployerConfigId"] = "2";

            prescriptionDict["PrescriberInfo.PrescriberNPI"] = PrescriberNPI;
            prescriptionDict["PrescriberInfo.PrescriberDEA"] = PrescriberDEA;
            prescriptionDict["PrescriberInfo.PrescriberName"] = PrescriberName;
            prescriptionDict["PrescriberInfo.PrescriberAddress"] = PrescriberAddress;
            prescriptionDict["PrescriberInfo.PrescriberCity"] = PrescriberCity;
            prescriptionDict["PrescriberInfo.PrescriberState"] = PrescriberState;
            prescriptionDict["PrescriberInfo.PrescriberZip"] = PrescriberZip;
            prescriptionDict["PrescriberInfo.PrescriberSpecialty"] = PrescriberSpecialty;
            prescriptionDict["PrescriberInfo.PrescriberOfficePhone"] = PrescriberOfficePhone;
            prescriptionDict["PrescriberInfo.PrescriberFax"] = PrescriberFax;
            prescriptionDict["PrescriberInfo.PrescriberRxUUID"] = rxUUID;

            prescriptionDict["PharmacyInfo.PharmacyName"] = pharmacyName;
            prescriptionDict["PharmacyInfo.PharmacyNPI"] = pharmacyNPI;
            prescriptionDict["PharmacyInfo.PharmacyNCPDP"] = pharmacyNCPDP;
            prescriptionDict["PharmacyInfo.PharmacyDEA"] = pharmacyDEA;
            prescriptionDict["PharmacyInfo.PharmacyAddress1"] = pharmacyAddress1;
            prescriptionDict["PharmacyInfo.PharmacyCity"] = pharmacyCity;
            prescriptionDict["PharmacyInfo.PharmacyState"] = pharmacyState;
            prescriptionDict["PharmacyInfo.PharmacyZIP"] = pharmacyZip;
            prescriptionDict["PharmacyInfo.PharmacyPhone"] = pharmacyPhone;
            prescriptionDict["PharmacyInfo.PharmacyFax"] = pharmacyFax;
            prescriptionDict["PharmacyInfo.PharmacyRxUUID"] = rxUUID;
            prescriptionDict["PharmacyInfo.PharmacyEmail"] = "revathi.pentakota@amzur.com";

            //if (InsChoice.ToLower() == "yes")
                GetInsuranceInfo(ref prescriptionDict, rxUUID);

            Console.Write("\nEnter NDC: ");
            string NDC = Console.ReadLine();

            if(string.IsNullOrWhiteSpace(NDC))
                NDC = GetRandomNDC();
            //string NDC = GetRandomNDC();

            prescriptionDict["RxTransaction.RxDrugName"] = GetRandomDrugName();
            prescriptionDict["RxTransaction.RxPrescriberAt"] = DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss");
            prescriptionDict["RxTransaction.RxSourceNDC"] = NDC;
            prescriptionDict["RxTransaction.RxFilledNDC"] = NDC;
            prescriptionDict["RxTransaction.RxDrugPrice"] = "50000";
            prescriptionDict["RxTransaction.RxQuantity"] = GetRandomQuantity();
            prescriptionDict["RxTransaction.RxQuantityUnit"] = "Tablet";  // Hardcoded for simplicity
            prescriptionDict["RxTransaction.RxDaysSupply"] = GetRandomDaysSupply();
            prescriptionDict["RxTransaction.RxCurrentRefill"] = GetRandomCurrentRefill();
            prescriptionDict["RxTransaction.RxDirections"] = GetRandomDirections();
            prescriptionDict["RxTransaction.RxDeliveryMethod"] = "Home Delivery";
            prescriptionDict["RxTransaction.RxAllowSubstitution"] = GetRandomBool();
            prescriptionDict["RxTransaction.RxDAW"] = GetRandomDAW();
            prescriptionDict["RxTransaction.RxPatientUUId"] = Guid.NewGuid();
            prescriptionDict["RxTransaction.RxPrescriberName"] = PrescriberName;
            prescriptionDict["RxTransaction.RxPrescriberDEA"] = PrescriberDEA;
            prescriptionDict["RxTransaction.RxPrescriberNPI"] = PrescriberNPI;
            prescriptionDict["RxTransaction.RxPrescriberAddress"] = PrescriberAddress;
            prescriptionDict["RxTransaction.RxPrescriberPhone"] = PrescriberPhone;
            prescriptionDict["RxTransaction.RxPrescriberCity"] = PrescriberCity;
            prescriptionDict["RxTransaction.RxPrescriberState"] = PrescriberState;
            prescriptionDict["RxTransaction.RxPrescriberZIP"] = PrescriberZip;
            prescriptionDict["RxTransaction.RxPrescriberSpecialty"] = PrescriberSpecialty;
            prescriptionDict["RxTransaction.RxPrescriberOfficePhone"] = PrescriberOfficePhone;
            prescriptionDict["RxTransaction.RxPharmacyName"] = pharmacyName;
            prescriptionDict["RxTransaction.RxPharmacyDEA"] = pharmacyDEA;
            prescriptionDict["RxTransaction.RxPharmacyNPI"] = pharmacyNPI;
            prescriptionDict["RxTransaction.RxPharmacyNCPDP"] = pharmacyNCPDP;
            prescriptionDict["RxTransaction.RxPharmacyAddress1"] = pharmacyAddress1;
            prescriptionDict["RxTransaction.RxPharmacyCity"] = pharmacyCity;
            prescriptionDict["RxTransaction.RxPharmacyState"] = pharmacyState;
            prescriptionDict["RxTransaction.RxPharmacyZIP"] = pharmacyZip;
            prescriptionDict["RxTransaction.RxPharmacyPhone"] = pharmacyPhone;
            prescriptionDict["RxTransaction.RxPharmacyFax"] = pharmacyFax;
            prescriptionDict["RxTransaction.RxIsDelivmedsUser"] = GetRandomBool();
            prescriptionDict["RxTransaction.RxUUID"] = rxUUID;
            prescriptionDict["RxTransaction.RxId"] = rxId;
            prescriptionDict["RxTransaction.RefillsAuthorized"] = 10;
            prescriptionDict["RxTransaction.RefillsRemaining"] = 10; 
            prescriptionDict["RxTransaction.RxLastDispensed"] = "2026-01-28";
            prescriptionDict["RxTransaction.RxAllergies"] = "Penicillin allergy";

            string jsonString = JsonConvert.SerializeObject(prescriptionDict, Newtonsoft.Json.Formatting.None);

            string finalJson = "{\"data\":\"" + jsonString.Replace("\"", "\\\"") + "\"}";
            // Print the generated JSON
            Console.WriteLine("\n\nGenerated JSON:");
            Console.WriteLine(finalJson);

            //Here I need API call to send this JSON to endpoint

            Console.ReadLine();
        }

        public static void GetInsuranceInfo(ref IDictionary<string, object> patientPrescription, Guid RxUUID)
        {
            string? insurancePCN = null, insuranceGroupNumber = null, insuranceMemberID = null, insurancePlanName = null;
            Guid insuranceRxUUID;
            var insuranceBIN = GetRandomInsuranceBIN();
            insurancePCN = GetRandomInsurancePCN();
            insuranceGroupNumber = GetRandomInsuranceGroupNumber();
            insuranceMemberID = GetRandomInsuranceMemberID();
            insurancePlanName = GetRandomInsurancePlanName();
            insuranceRxUUID = RxUUID;

            // Insurance data reused for RxInsurance
            patientPrescription["InsuranceInfo.InsuranceBIN"] = insuranceBIN;
            patientPrescription["InsuranceInfo.InsurancePCN"] = insurancePCN;
            patientPrescription["InsuranceInfo.InsuranceGroupNumber"] = insuranceGroupNumber;
            patientPrescription["InsuranceInfo.InsuranceMemberID"] = insuranceMemberID;
            patientPrescription["InsuranceInfo.InsurancePlanName"] = insurancePlanName;
            patientPrescription["InsuranceInfo.InsuranceRxUUID"] = RxUUID;
            patientPrescription["InsuranceInfo.InsuranceType"] = GetRandomInsuranceType();
            patientPrescription["RxTransaction.RxInsuranceBIN"] = insuranceBIN;
            patientPrescription["RxTransaction.RxInsurancePCN"] = insurancePCN;
            patientPrescription["RxTransaction.RxInsuranceGroupNumber"] = insuranceGroupNumber;
            patientPrescription["RxTransaction.RxInsuranceMemberID"] = insuranceMemberID;
            patientPrescription["RxTransaction.RxInsurancePlanName"] = insurancePlanName;
        }

        // Helper methods to generate random values for fields
        public static string GetRandomPrescriberName()
        {
            string[] firstNames = { "Sophia", "James", "Ava", "Michael", "Sarah", "David", "Olivia", "John", "Emma", "William" };
            string[] lastNames = { "Martinez", "Smith", "Johnson", "Davis", "Wilson", "Brown", "Taylor", "Anderson", "Moore", "Jackson" };

            string firstName = firstNames[new Random().Next(firstNames.Length)];
            string lastName = lastNames[new Random().Next(lastNames.Length)];

            // Prefix "Dr." to the name
            return $"Dr. {firstName} {lastName}";
        }
        public static string GetRandomPatientFirstName()
        {
            string[] firstNames = { "David", "Emma", "James", "Olivia", "John", "Sophia", "Michael", "Ava", "William", "Sarah" };
            return firstNames[new Random().Next(firstNames.Length)];
        }

        public static string GetRandomPatientLastName()
        {
            string[] lastNames = { "Wilson", "Johnson", "Davis", "Brown", "Taylor", "Anderson", "Moore", "Jackson", "Martin", "Lee" };
            return lastNames[new Random().Next(lastNames.Length)];
        }

        public static string GetRandomDateOfBirth() => new DateTime(new Random().Next(1950, 2000), new Random().Next(1, 13), new Random().Next(1, 29)).ToString("yyyy-MM-dd");
        public static string GetRandomGender() => new Random().Next(0, 2) == 0 ? "M" : "F";
        public static string GetRandomPhoneNumber() => "+14079006176";
            //$"{new Random().Next(100, 999)}{new Random().Next(100, 999)}{new Random().Next(1000, 9999)}";
        public static string GetRandomAddress() => $"{new Random().Next(100, 999)} Main St";
        public static string GetRandomSSN() => $"{new Random().Next(100, 999)}{new Random().Next(10, 99)}{new Random().Next(1000, 9999)}";
        public static string GetRandomCity() => "City" + new Random().Next(1, 100);
        public static string GetRandomState() => new Random().Next(0, 2) == 0 ? "FL" : "CA";
        public static string GetRandomZip() => $"{new Random().Next(10000, 99999)}";
        public static string GetRandomNPI() => $"{new Random().NextInt64(1000000000, 9999999999)}";   
        public static string GetRandomDEA() => $"{(char)new Random().Next(65, 91)}{new Random().Next(10000000, 99999999)}";
        public static string GetRandomSpecialty() => "General Medicine";
        public static string GetRandomWebsite() => "http://www.randompharmacy.com";
        public static string GetRandomPharmacyName() => "HealthCare Pharmacy";
        public static string GetRandomNCPDP() => $"{new Random().Next(1000000, 9999999)}";
        //static string GetRandomNCPDP() => "1234567";
        public static string GetRandomDispenseMethod() => new Random().Next(0, 2) == 0 ? "Mail Order" : "Pickup";
        //static string GetRandomInsuranceBIN() => $"{new Random().Next(100000, 999999)}";


        // public static string GetRandomInsuranceBIN()
        //{
        //    string[] lstInsBIN = { "610502", "800010", "606464", "610311", "610602", "220026", "610228", "610862", "800008" };
        //    return lstInsBIN[new Random().Next(lstInsBIN.Length)];
        //}

        //public static string GetRandomInsuranceBIN() => $"{(char)new Random().Next(65, 91)}{new Random().Next(10000000, 99999999)}";

        public static string GetRandomInsuranceBIN() => $"{new Random().Next(100000, 1000000)}";

        //private static readonly Random _rand = new Random(); 
        //public static string GetRandomInsuranceBIN()
        //{
        //    return _rand.Next(100000, 1000000).ToString(); // 6-digit number
        //}

        public static string GetRandomInsurancePCN() => $"PCN{new Random().Next(1000, 9999)}";
        public static string GetRandomInsuranceGroupNumber() => $"GRP{new Random().Next(1000, 9999)}";
        public static string GetRandomInsuranceMemberID() => $"MEM{new Random().Next(100000, 999999)}";
        public static string GetRandomInsurancePlanName() => "Plan" + new Random().Next(1, 10);
        //public static string GetRandomDrugName() => "Metformin " + new Random().Next(10, 100) + " Mg Oral Tablet";
        public static string GetRandomDrugName() => "JARDIANCE ORAL TAB 10MG";
        //static string GetRandomNDC() => $"{new Random().Next(10000000, 99999999)}";
        public static string GetRandomNDC() => "82381217402"; //"00597015230";//"82381217402";////"82381217402";// "90861617";
        public static int GetRandomQuantity() => new Random().Next(1, 100);
        public static string GetRandomDaysSupply() => new Random().Next(10, 100).ToString();
        public static string GetRandomCurrentRefill() => new Random().Next(1, 10).ToString();
        public static string GetRandomDirections() => "Take 10 tablet twice a day as needed for pain.";
        public static string GetRandomBool() => new Random().Next(0, 2) == 0 ? "True" : "False";
        public static string GetRandomDAW() => "1";  // Default DAW code
        public static int GetRandomRxId() => new Random().Next(1, 10000);

        public static string GetRandomInsuranceType()
        {

            string[] lstInsuranceTypes = { "Medicare", "Medicaid", "Private Insurance", "Employer-Sponsored Insurance", "Dual Eligible" };

            string InsuranceType = lstInsuranceTypes[new Random().Next(lstInsuranceTypes.Length)];

            return InsuranceType;
        }
    }
} 