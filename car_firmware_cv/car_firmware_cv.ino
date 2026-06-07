#include <WiFi.h>
#include "esp_camera.h"
#include <ACB_SmartCar_V2.h>
#include <ultrasonic.h>
#include <ESP32Servo.h>
#include <ACB_CanMV.h>
#include <Arduino.h>

#define Yservo_PIN     25 // Camera height

#define Left_Line 35      //Left   Line patrol Pin
#define Center_Line 36    //center Line patrol Pin
#define Right_Line 39     //Right  Line patrol Pin
#define Buzzer 33         //Buzzer Pin

#define CMD_RUN 1      //Motion marker bit
#define CMD_STANDBY 3  //Task flag bit
#define CMD_TRACK_1 4  //Patrol duty 1 mode
#define CMD_TRACK_2 5  //Patrol duty 2 mode


#define CMD_Qr_code                30       // QR code recognition
#define CMD_Barcode                31       // Barcode recognition
#define CMD_Digital_recognition    32       // Digital recognition

#define CMD_Color_recognition      33       // Color recognition
#define CMD_Image_recognition      34       // Image recognition

#define CMD_Color_tracking         35       // Color tracking
#define CMD_Visual_inspection      36       // Visual line inspection
#define CMD_Traffic_identification 37       // Traffic identification
#define CMD_Machine_learning       38       // Machine learning
#define CMD_Face_recognition       39       // Face recognition

#define CMD_GRB_RED                41       //RGB red
#define CMD_GRB_GREEN              42       //RGB green
#define CMD_GRB_BLUE               43       //RGB blue

#define CMD_Take_Stop              50       // Stop

//app music
#define C3 131
#define D3 147
#define E3 165
#define F3 175
#define G3 196
#define A3 221
#define B3 248

#define C4 262
#define D4 294
#define E4 330
#define F4 350
#define G4 393
#define A4 441
#define B4 495

#define C5 525
#define D5 589
#define E5 661
#define F5 700
#define G5 786
#define A5 882
#define B5 990
#define N 0

const char *ssid = "ESP32_QD003"; //Set WIFI name
const char *password = "12345678"; //Set WIFI password
WiFiServer server(100); //Setting the server port

WiFiClient client; //Client side
ACB_SmartCar_V2 Acebott; //car
Servo Yservo; //Servo
ACB_CanMV acb_canmv;

String Trafic_tag;       // Store traffic tags

int Left_Tra_Value;      // The value of the patrol sensor on the left side
int Center_Tra_Value;    // Intermediate line inspection sensor value
int Right_Tra_Value;     // The value of the line inspection sensor on the right side
int Black_Line = 2000;   // The threshold for detecting the black line
int Off_Road = 4000;
int speeds = 250;        // Preset speed: 250

char red   = 0;          // Save the GRB in red state
char green = 0;          // Save the GRB green state
char blue  = 0;          // Save the GRB blue state

uint8_t data[5]; 

const int X_STOP_MIN = 30;    // Preset left turn range 
const int X_STOP_MAX = 240;  // Preset right turn range 
const int H_STOP_MIN = 50;    // Preset forward range 
const int H_STOP_MAX = 70;    // Preset backward range 


String sendBuff;
byte dataLen, index_a = 0;
char buffer[52];
unsigned char prevc=0;
bool isStart = false;
bool ED_client = true;
bool WA_en = false;
uint16_t angle = 90;
byte action = Stop, device;
byte val = 0;

unsigned long Trafic_lastTagChangeTime = 0; // Record the last recognition time 
unsigned long Color_lastTagChangeTime = 0;  // Record the last recognition time 

int length0;
int length1;
int length2;
int length3;
//****app music****
// littel star
int tune0[] = { C4, N, C4, G4, N, G4, A4, N, A4, G4, N, F4, N, F4, E4, N, E4, D4, N, D4, C4 };
float durt0[] = { 0.99, 0.01, 1, 0.99, 0.01, 1, 0.99, 0.01, 1, 1.95, 0.05, 0.99, 0.01, 1, 0.99, 0.01, 1, 0.99, 0.01, 1, 2 };
// jingle bell
int tune1[] = { E4, N, E4, N, E4, N, E4, N, E4, N, E4, N, E4, G4, C4, D4, E4 };
float durt1[] = { 0.49, 0.01, 0.49, 0.01, 0.99, 0.01, 0.49, 0.01, 0.49, 0.01, 0.99, 0.01, 0.5, 0.5, 0.75, 0.25, 1, 2};
// happy new year
int tune2[] = { C5, N, C5, N, C5, G4, E5, N, E5, N, E5, C5, N, C5, E5, G5, N, G5, F5, E5, D5, N };
float durt2[] = { 0.49, 0.01, 0.49, 0.01, 1, 1, 0.49, 0.01, 0.49, 0.01, 1, 0.99, 0.01, 0.5, 0.5,0.99,0.01, 1, 0.5, 0.5, 1, 1 };
// have a farm
int tune3[] = { C4, N, C4, N, C4, G3, A3, N, A3, G3,  E4, N, E4, D4, N, D4, C4 };
float durt3[] = { 0.99, 0.01, 0.99, 0.01, 1, 1, 0.99, 0.01, 1, 2, 0.99, 0.01, 1, 0.99, 0.01, 1, 1 };
//****app music****

unsigned long lastDataTimes = 0;
bool st = false;

unsigned char readBuffer(int index_r)
{
  return buffer[index_r]; 
}
void writeBuffer(int index_w,unsigned char c)
{
  buffer[index_w]=c;
}

enum FUNCTION_MODE
{
  STANDBY,
  TRACK_1,
  TRACK_2,

  QR_CODE,
  BARCODE,
  DIGITAL_RECOG,
  COLOR_RECOG,
  IMAGE_RECOG,
  COLOR_TRACKING,
  VISUAL_INSPECTION,
  TRAFFIC_IDENT,
  MACHINE_LEARNING,
  FACE_RECOG,

} function_mode;

void setup()
{
    Serial.setTimeout(10);  // Set the serial port timeout to 10 milliseconds
    Serial.begin(115200);  // Serial communication is initialized with a baud rate of 115200

    Acebott.Init();  // Initialize Acebott

    pinMode(Left_Line, INPUT);  // Set infrared left line pin as input
    pinMode(Center_Line, INPUT);  // Set the infrared middle line pin as input
    pinMode(Right_Line, INPUT);  // Set the right infrared line pin as input

    ESP32PWM::allocateTimer(1);  // Assign timer 1 to the ESP32PWM library
    Yservo.attach(Yservo_PIN);  // Connect the servo to the Yservo_PIN pin
    Yservo.write(angle);  // Set the steering angle as Angle
    Acebott.Move(Stop, 0);  // Stop the Acebott exercise

    length0 = sizeof(tune0) / sizeof(tune0[0]);  // Calculate the length of the tune0 array
    length1 = sizeof(tune1) / sizeof(tune1[0]);  // Calculate the length of the tune1 array
    length2 = sizeof(tune2) / sizeof(tune2[0]);  // Calculate the length of the tune2 array
    length3 = sizeof(tune3) / sizeof(tune3[0]);  // Calculate the length of the tune3 array

    WiFi.setTxPower(WIFI_POWER_19_5dBm);  // The Wi-Fi transmit power is set to 19.5dBm
    WiFi.mode(WIFI_AP);  // Set the Wi-Fi operating mode to access point mode
    WiFi.softAP(ssid, password, 5);  // Create a Wi-Fi access point with SSID as ssid, password as password, and maximum number of connections as 5
    Serial.print("\r\n");
    Serial.print("Camera Ready! Use 'http://");  // Printing a prompt
    Serial.print(WiFi.softAPIP());  // Print the access point IP address
    Serial.println("' to connect");  // Printing a prompt

    delay(100);

    server.begin();  // Starting the server

    acb_canmv.init(SDA,SCL);     //Camera initialization

    delay(1000);                 // Power on and wait for 1 second to start up

    acb_canmv.Default_menu();    // Enter the menu interface

}

void loop()
{
    RXpack_func();
}

void functionMode()
{
    switch (function_mode)
    {

        case TRACK_1:
        {
            model1_func();  // Go into trace mode 1 and call the model1_func() function
        }
        break;
        case TRACK_2:
        {
            model4_func();  // Enter trace mode 2 and call the model4_func() function
        }
        break;  

        case COLOR_TRACKING:
        {
            Color_Tracking_Task();      // Color tracking mode

        } 
        break;
        case QR_CODE:                  
        {
          if(acb_canmv.qrcode_recognize()) {           //Qr code recognition mode
              Serial.println(acb_canmv.getTag());
            }
          
        }  
        break;
        case BARCODE:
        {
          if(acb_canmv.barcode_recognize()) {           // Barcode recognition mode
            Serial.println(acb_canmv.getTag());
          }
        }
        break;

        case DIGITAL_RECOG:
        {
          if(acb_canmv.number_recognize()) {          // Digital recognition mode
            Serial.println(acb_canmv.getTag());
          }
        }
        break;

        case COLOR_RECOG:
        {
         if(acb_canmv.color_recognize(0,400)) {       // Color recognition mode
            Serial.println(acb_canmv.getTag());
          }
        }
        break;  

        case IMAGE_RECOG:
        {
         if(acb_canmv.image_recognize()) {            // Image recognition mode
            Serial.println(acb_canmv.getTag());
          }
        }
        break;

        case VISUAL_INSPECTION:
        {  
          Visual_Patrol_Task();                      // Visual line inspection mode
        }
        break;                

        case TRAFFIC_IDENT:
        {
          Trafic_Sign_Task();                        // Traffic recognition mode
        }
        break;

        case MACHINE_LEARNING:                     
        {
         if(acb_canmv.machine_learning()) {          // Machine learning mode
            Serial.println(acb_canmv.getTag());
          }
        }
        break;

        case FACE_RECOG:
        {
         if(acb_canmv.face_recognize()) {            // Face recognition mode
            Serial.println(acb_canmv.getTag());
          }
        }
        break;   

        default:
            break;
    }
}

void Color_Tracking_Task(){    // Color tracking

    if(acb_canmv.color_recognize(readBuffer(12), 600)) { // Identify colors
        int x = acb_canmv.getX();                        // Control the left/right rotation range of the trolley
        int H = acb_canmv.getH();                        // Control the front and rear range of the car

       if(x >= X_STOP_MIN && x <= X_STOP_MAX && H >= H_STOP_MIN && H <= H_STOP_MAX ) {
            Acebott.Move(Stop, 0);
        }

       if(H > H_STOP_MAX) {
            Acebott.Move( Backward, 150);
        } else if(H < H_STOP_MIN) {
            Acebott.Move(Forward, 150);
        } 

        if(x > X_STOP_MAX) {
            Acebott.Move(Clockwise, 150);
        } else if(x < X_STOP_MIN) {
            Acebott.Move(Contrarotate, 150);
        }

      Color_lastTagChangeTime = millis();                                     // Obtain the last running time 
    }

    if(millis() - Color_lastTagChangeTime > 200) Acebott.Move(Stop, 0);       // Automatic stop if no image is obtained within 200 milliseconds 

}

void Visual_Patrol_Task(){

  Yservo.write(35);
  if(acb_canmv.visual_patrol()) {   
    int visualData = acb_canmv.Visual_data();        // Obtain the tracking value
    
    if (visualData < -10 && visualData >= -50) {     //Follow the path to the right
      Acebott.Move(Stop, 0);
      delay(30);
      Acebott.Move( Clockwise, 140);
      
    } 
    else if (visualData <= 15 && visualData >= -10) {  // Forward

      Acebott.Move(Forward, 150);
      
    } 
    else if (visualData <= 52 && visualData > 15){    // Trace to the left
      Acebott.Move(Stop, 0);
      delay(30);
      Acebott.Move(Contrarotate, 140);
    }
    else{ Acebott.Move(Backward, 140);delay(10);}   // After the display recognition exceeds, back off to look for the black line
  }

}

void Trafic_Sign_Task() {  // Perform corresponding actions according to the recognized traffic signs
    Yservo.write(90);        

    if(acb_canmv.Traffic_recognize()) { // Traffic identification task

    Trafic_tag = acb_canmv.getTag();    // Save the recognized traffic tags

    Serial.println(acb_canmv.getTag()); // Print the recognized traffic Tag

    Trafic_lastTagChangeTime = millis();
  }

    if(Trafic_tag != "None" && (millis() - Trafic_lastTagChangeTime > 500) ) { // Detect the traffic tag and start it 500 milliseconds after the tag leaves 
    
    if(Trafic_tag == "Go_Straight") {        // Move forward 
        Acebott.Move(Forward, 180);
        delay(500);
    } 
    
    else if(Trafic_tag == "Turn_Right") {    // Turn right 
        Acebott.Move(Clockwise, 180);
        delay(500);
    } 
    
    else if(Trafic_tag == "Turn_Left") {     // Turn left 
        Acebott.Move(Contrarotate, 180);
        delay(500);
    } 
    
    else if(Trafic_tag == "Turn_Around") {   // Go straight and turn around 
        Acebott.Move(Forward, 180);
        delay(1450);
        Acebott.Move(Clockwise, 180);
        delay(1600);
        Acebott.Move(Forward, 180);
        delay(1300);
    } 
    
    else if(Trafic_tag == "Throughout") {     // No entry 
        Acebott.Move(Stop, 180);
        delay(500);
    }

    Trafic_tag = "None";
    Acebott.Move(Stop, 180);

    }
}

void Receive_data()  // Receiving data
{
    if (client.available())  // If data is available
    {
        unsigned char c = client.read() & 0xff;  // Read a byte of data
        Serial.write(c);  // Send the received data on the serial port
        lastDataTimes = millis(); // 
        if (c == 200)
        {
          st = false;
        }
        if (c == 0x55 && isStart == false)  // If the start flag 0x55 is received and data has not yet been received
        {
            if (prevc == 0xff)  // If the previous byte is also the start flag 0xff
            {
                index_a = 1;  // The data index is set to 1
                isStart = true;  // Start receiving data
            }
        }
        else
        {
            prevc = c;  // Update the previous byte's value
            if (isStart)  // If data has already been received
            {
                if (index_a == 2)  // If it is the second byte, it is the length of the data
                {
                    dataLen = c;  // Update data length
                }
                else if (index_a > 2)  // If it's a subsequent byte
                {
                    dataLen--;  // The data length is decremented by one
                }
                writeBuffer(index_a, c);  // Writes data to the buffer
            }
        }
        index_a++;  // Index increase
        if (index_a > 120)  // If the index exceeds the upper limit
        {
            index_a = 0;  // Reset the index to 0
            isStart = false;  // End of data reception
        }
        if (isStart && dataLen == 0 && index_a > 3)  // If the data is received
        { 
            isStart = false;  // End of data reception
            parseData();  // Parsing data
            index_a = 0;  // Reset the index to 0
        }
    }
    if (client.available() == 0 && (millis() - lastDataTimes)>3000)
    {
      st = true;
    }
}
void model4_func()      // tracking model2
{
    Yservo.write(90);
    Left_Tra_Value = analogRead(Left_Line);
    Center_Tra_Value = analogRead(Center_Line);
    Right_Tra_Value = analogRead(Right_Line);
    delay(5);
    if (Left_Tra_Value < Black_Line && Center_Tra_Value >= Black_Line && Right_Tra_Value < Black_Line)
    {
        Acebott.Move(Forward, 180);
    }
    if (Left_Tra_Value < Black_Line && Center_Tra_Value >= Black_Line && Right_Tra_Value >= Black_Line)
    {
        Acebott.Move(Forward, 180);
    }
    if (Left_Tra_Value >= Black_Line && Center_Tra_Value >= Black_Line && Right_Tra_Value < Black_Line)
    {
        Acebott.Move(Forward, 180);
    }
    else if (Left_Tra_Value >= Black_Line && Center_Tra_Value < Black_Line && Right_Tra_Value < Black_Line)
    {
        Acebott.Move(Contrarotate, 220);
    }
    else if (Left_Tra_Value < Black_Line && Center_Tra_Value < Black_Line && Right_Tra_Value >= Black_Line)
    {
        Acebott.Move(Clockwise, 220);
    }
    else if (Left_Tra_Value >= Off_Road && Center_Tra_Value >= Off_Road && Right_Tra_Value >= Off_Road)
    {
        Acebott.Move(Stop, 0);
    }
}
void model1_func()      // tracking model1
{
    
    Left_Tra_Value = analogRead(Left_Line);
   
    Right_Tra_Value = analogRead(Right_Line);
   
    delay(5);
    if (Left_Tra_Value < Black_Line && Right_Tra_Value < Black_Line)
    {
        Acebott.Move(Forward, 180);
    }
    else if (Left_Tra_Value >= Black_Line && Right_Tra_Value < Black_Line)
    {
        Acebott.Move(Contrarotate, 150);
    }
    else if (Left_Tra_Value < Black_Line && Right_Tra_Value >= Black_Line)
    {
        Acebott.Move(Clockwise, 150);
    }
    else if (Left_Tra_Value >= Black_Line && Left_Tra_Value < Off_Road && Right_Tra_Value >= Black_Line && Right_Tra_Value < Off_Road)
    {
        Acebott.Move(Stop, 0);
    }
    else if (Left_Tra_Value >= Off_Road && Right_Tra_Value >= Off_Road)
    {
        Acebott.Move(Stop, 0);
    }
}
void Servo_Move(int angles)  //servo
{
  Yservo.write(angles);
  if (angles >= 180) angles = 180;
  if (angles <= 1) angles = 1;
  delay(10);
}
void Music_a()
{
    for(int x=0;x<length0;x++) 
    { 
        tone(Buzzer, tune0[x]);
        delay(500 * durt0[x]);
        noTone(Buzzer);
    }
}
void Music_b()
{
    for(int x=0;x<length1;x++) 
    { 
        tone(Buzzer, tune1[x]);
        delay(500 * durt1[x]);
        noTone(Buzzer);
    }
}
void Music_c()
{
    for(int x=0;x<length2;x++) 
    { 
        tone(Buzzer, tune2[x]);
        delay(500 * durt2[x]);
        noTone(Buzzer);
    }
}
void Music_d()
{
    for(int x=0;x<length3;x++) 
    { 
        tone(Buzzer, tune3[x]);
        delay(300 * durt3[x]);
        noTone(Buzzer);
    }
}
void Buzzer_run(int M)
{
    switch (M)
    {
        case 0x01:
            Music_a();
            break;
        case 0x02:
            Music_b();
            break;
        case 0x03:
            Music_c();
            break;
        case 0x04:
            Music_d();
            break;
        default:
            break;
    }
}

void runModule(int device)
{
  val = readBuffer(12);
  switch(device) 
  {
    case 0x0C:
    {   
      switch (val)
      {
        case 0x01:
            Acebott.Move(Forward, speeds);
            break;
        case 0x02:
            Acebott.Move(Backward, speeds);
            break;
        case 0x03:
            Acebott.Move(Move_Left, speeds);
            break;
        case 0x04:
            Acebott.Move(Move_Right, speeds);
            break;
        case 0x05:
            Acebott.Move(Top_Left, speeds);
            break;
        case 0x06:
            Acebott.Move(Bottom_Left, speeds);
            break;
        case 0x07:
            Acebott.Move(Top_Right, speeds);
            break;
        case 0x08:
            Acebott.Move(Bottom_Right, speeds);
            break;
        case 0x0A:
            Acebott.Move(Clockwise, speeds);
            break;
        case 0x09:
            Acebott.Move(Contrarotate, speeds);
            break;
        case 0x00:
            Acebott.Move(Stop, 0);
            break;
        default:
            break;
      }
    }break;
    case 0x02:
    {  
        Servo_Move(val);
    }break;
    case 0x03:
    {  
        Buzzer_run(val);
    }break;
    case 0x0D:
    {
        speeds = val;
    }break;
  }   
}

void parseData() { 
    isStart = false;
    int action = readBuffer(9);
    int device = readBuffer(10);  
    Yservo.write(90);
    Acebott.Move(Stop, 0);                  

    switch (action) {
        case CMD_RUN:
            function_mode = STANDBY;
            runModule(device);
            break;
            
        case CMD_STANDBY:
            function_mode = STANDBY;
            Acebott.Move(Stop, 0);
            Yservo.write(90);
            break;
            
        case CMD_TRACK_1:
            function_mode = TRACK_1;
            break;
            
        case CMD_TRACK_2:
            function_mode = TRACK_2;
            break;
            
        default:
            break;   
    }       
    switch (device) {
      
        case CMD_Qr_code:                       // QR code recognition   
            function_mode = QR_CODE;
            break;
            
        case CMD_Barcode:                       // Barcode recognition    
            function_mode = BARCODE;
            break;
            
        case CMD_Digital_recognition:           // Digital recognition
            function_mode = DIGITAL_RECOG;
            break;
            
        case CMD_Color_recognition:             // Color recognition
            function_mode = COLOR_RECOG;
            break;
            
        case CMD_Image_recognition:             // Image recognition
            function_mode = IMAGE_RECOG;
            break;
            
        case CMD_Color_tracking:                // Color tracking
            function_mode = COLOR_TRACKING;
            break;
          
        case CMD_Visual_inspection:             // Visual line inspection
            function_mode = VISUAL_INSPECTION;
            break;
            
        case CMD_Traffic_identification:        // Traffic identification
            function_mode = TRAFFIC_IDENT;
            break;
            
        case CMD_Machine_learning:              // Machine recognition
            function_mode = MACHINE_LEARNING;
            break;
            
        case CMD_Face_recognition:              // Face recognition
            function_mode = FACE_RECOG;
            break;
            
        case CMD_GRB_RED:

            red = int(readBuffer(12));
            
            acb_canmv.RGB_set(red,green,blue); 
            break;
            
        case CMD_GRB_GREEN:

            green = int(readBuffer(12));
            acb_canmv.RGB_set(red,green,blue); 
            break;
            
        case CMD_GRB_BLUE:

            blue = int(readBuffer(12));
            acb_canmv.RGB_set(red,green,blue); 
            break;      

        case CMD_Take_Stop:
            acb_canmv.Default_menu();         // Return to the menu
            Acebott.Move(Stop, 0);            // Stop the car
             
            break;
            
        default:
            break;
    }
    
}

void RXpack_func()  // Receiving data
{
  client = server.available();  // Wait for the client to connect
  if (client)  // If there is a client connection
  {
    WA_en = true;  // Enable the write enable
    ED_client = true;  // The client connection flag is set to true
    Serial.println("[Client connected]");  // Print client connection information
    unsigned long previousMillis = millis();  // 
    const unsigned long timeoutDuration = 3000;  // 
    while (client.connected())  // While the client is still connected
    {
      if ((millis() - previousMillis) > timeoutDuration && client.available() == 0 && st == true)
      {
        break;
      }
      if (client.available())  // If there is data to read
      {
        previousMillis = millis();
        unsigned char c = client.read() & 0xff;  // Reading data
        // Serial.print("Received byte: 0x");  // Printing received byte in hexadecimal
        // Serial.println(c, DEC);  // Print the received data as hexadecimal value
        // Serial.print("\n");
        st = false;
        if (c == 200)
        {
          st = true;
        }
        if (c == 0x55 && isStart == false)  // If the data received is 0x55 and isStart is false
        {
          if (prevc == 0xff)  // If the previous byte is 0xff
          {
            index_a = 1;  // The index is set to 1
            isStart = true;  // The data start flag is set to true
          }
        }
        else
        {
          prevc = c;  // Update the previous byte's value
          if (isStart)  // If the data start flag is true
          {
            if (index_a == 2)  // If the index is 2
            {
              dataLen = c;  // The data length is set to c
            }
            else if (index_a > 2)  // If the index is greater than 2
            {
              dataLen--;  // The data length is decremented by 1
            }
            writeBuffer(index_a, c);  // Writes data to the buffer
          }
        }
        index_a++;  // Index incremented by 1
        if (index_a > 120)  // If the index is greater than 120
        {
          index_a = 0;  // The index is reset to 0
          isStart = false;  // The data start flag is set to false
        }
        if (isStart && dataLen == 0 && index_a > 3)  // If the data start flag is true and the data length is 0 and the index is greater than 3
        {
          isStart = false;  // The data start flag is set to false
          parseData();  // Parsing data
          index_a = 0;  // The index is set to 0
        }
      }
      functionMode();  // Function-pattern processing
      if (Serial.available())  // If the serial port has data to read
      {
        char c = Serial.read();  // Reading data
        sendBuff += c;  // Add the data to the send buffer
        client.print(sendBuff);  // Send the data to the client
        sendBuff = "";  // Clear the send buffer
      }
    }
    client.stop();  // Disconnect the client
    Acebott.Move(Stop, 0);
    Serial.println("[Client disconnected]");  // Prints client disconnection information
  }
  else  // If there is no client connection
  {
    if (ED_client == true)  // If there was a previous client connection
    {
      ED_client = false;  // The client connection flag is set to false
    }
  }
}