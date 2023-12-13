import sys
import os
import time
import datetime
import re
import subprocess
import argparse
from colorama import Fore, Back, Style
import json
from enum import Enum

import openai
from azure.identity import AzureCliCredential

# Constants
OPENAI_API_BASE                 = 'https://openai-content-selfserv.openai.azure.com/'
OPENAI_VERSION                  = '2023-07-01-preview' # This may change in the future.
OPENAI_API_TYPE                 = 'azure_ad'
OPENAI_ENGINE                   = 'gpt-4-32k-moreExpensivePerToken'

openai.api_base     = OPENAI_API_BASE
openai.api_version  = OPENAI_VERSION

credential = AzureCliCredential()
token = credential.get_token("https://cognitiveservices.azure.com/.default")

openai.api_type     = OPENAI_API_TYPE
openai.api_key      = token.token
        
TEST_RECORD_FILE_NAME           = 'TestRecord.md'

# Globals
sample_inputs_source            = []
sample_outputs_source           = []
debug_mode                      = False

new_sample_input_dir            = ''
new_sample_output_dir           = ''
application_path                = ''

class PrintDisposition(Enum):
    SUCCESS = 1
    WARNING = 2
    ERROR   = 3
    STATUS  = 4

def print_message(text = '', disp = PrintDisposition.STATUS):
    if disp == PrintDisposition.SUCCESS:
        color = Fore.GREEN
    elif disp == PrintDisposition.WARNING:
        color = Fore.YELLOW
    elif disp == PrintDisposition.ERROR:
        color = Fore.RED
    else: # Status only
        color = Fore.WHITE

    print(color + text + Style.RESET_ALL)

def write_file(file_name, contents):
    try:
        with open(file_name, "w") as f:
            f.write(contents)
    except OSError as error:
        print_message(f"Failed to write file: {error}", PrintDisposition.ERROR)

def write_dictionary_to_file(file_name, dictionary):
    try:
        with open(file_name, "w") as f:
            f.write(json.dumps(dictionary, indent=4))
    except OSError as error:
        print_message(f"Failed to write file: {error}", PrintDisposition.ERROR)

def generate_new_sample():
    print_message("Generating new sample...")

    completion = ''

    try:
        print_message("\tCreating prompt...")

        messages = []

        for i in range(len(sample_inputs_source)-1):
            messages.append({"role": "user", "content": sample_inputs_source[i]})
            messages.append({"role": "assistant", "content": sample_outputs_source[i]})
        messages.append({"role": "user", "content": sample_inputs_source[i+1]})

        if debug_mode:
            write_dictionary_to_file('prompt.json', messages)

        print_message("\tCalling OpenAI...")
        time.sleep(1)
        return ""
        response = openai.ChatCompletion.create(engine=OPENAI_ENGINE,
                                                messages=messages,
                                                temperature=0
                                                )
                                                
        if response:
            completion = response.choices[0].message.content.rstrip()
    except OSError as error:
        print_message(f"Failed to generate new sample. {error}", PrintDisposition.ERROR)

    time.sleep(1)

    if debug_mode:
        write_file('completion.txt', completion)
    
    return completion

def get_input_source(args):
    print_message("Validating input args...")

    success = True

    try:
        # Open the Inputs file.
        with open('inputs.json') as inputs_file:
            # Load the JSON inputs file.
            inputs = json.load(inputs_file)

            # Each line is an input and there needs to be at least one line (input).
            if 1 > len(inputs):
                print_message('At least one input/output pair must be specified in the inputs file.', PrintDisposition.ERROR)
                success = False
    except OSError as error:
        print_message(f"Failed to open inputs file. {error}", PrintDisposition.ERROR)
        success = False

    # If the Inputs file successfully opened...
    if success:
        print_message("Processing input file...")

        # For each line in the file (representing a sample)...
        for i, (input, output) in enumerate(inputs.items()):
            print_message(f"\tInput dir:{input}")
            print_message(f"\tOutput dir:{output}")
            print_message()
            sample_inputs_source.append(get_terraform_source_code(input))
            sample_outputs_source.append(get_terraform_source_code(output))

        # If the specified sample dir exists...
        new_sample_input_dir = args.sample_directory
        if file_exists(new_sample_input_dir):

            try:
                if not os.path.exists(new_sample_output_dir):
                    os.mkdir(new_sample_output_dir)

                # Add the sample dir to the list.
                sample_inputs_source.append(get_terraform_source_code(new_sample_input_dir))
            except OSError as error:
                print_message(f"Failed to create output directory. {error}", PrintDisposition.ERROR)
                success = False
        else:

            print_message(f"Sample directory not found: {new_sample_input_dir}", PrintDisposition.ERROR)
            
            success = False

    return success

def list_to_string(input_list):

    # Initialize an empty string.
    return_string = ""

    # Traverse elements of list...
    for list_element in input_list:

        # Add element to string.
        return_string += list_element

    # Return string.
    return return_string

def get_file_contents(file):
    file_contents = ""

    with open(file, encoding="utf-8") as f:
        file_contents = f.readlines()

    file_contents = list_to_string(file_contents)
    return file_contents

def get_terraform_source_code(dir):
    current_sample_source_code = ""

    # For every file in the source directory...
    for file_name in os.listdir(dir):

        # DO NOT process TestRecord.md file...
        if file_name != TEST_RECORD_FILE_NAME and file_name != '':
            # Append source code for the current directory/file
            current_file_source_code = ("###" 
            + file_name 
            + "###" 
            + "\n" 
            + get_file_contents(os.path.join(dir, file_name))
            + "\n" 
            + file_name 
            + ":end\n")

            current_sample_source_code += current_file_source_code

    # Return the source code for the specified directory.
    return current_sample_source_code

def file_exists(path):
    return os.path.exists(path)

def parse_args():
    # Configure argParser for user-supplied arguments.

    print_message("Parsing args...")

    argParser = argparse.ArgumentParser()
    argParser.add_argument("-s", 
                           "--sample_directory", 
                           help="Name of input sample directory.", 
                           required=True)

    argParser.add_argument("-d", 
                           "--debug", 
                           action=argparse.BooleanOptionalAction,
                           help="Outputs files to help with debugging.", 
                           required=False)

    return argParser.parse_args()

def create_new_sample():
    print_message("Creating new sample...")

    success = True

    completion = generate_new_sample()

    if completion:
        file_names = re.findall(r'###(.*)###', completion)

        if file_names:
            for i in range(len(file_names)):
                current_file = file_names[i]

                beg_m = re.search('###'+ current_file + '###', completion)
                if beg_m:
                    end_m = re.search(current_file + ':end', completion)
                    if end_m:
                        sub = completion[(beg_m.span())[1]:(end_m.span())[0]]
                        sub = sub.strip()

                        curr_qfn = os.path.join(new_sample_output_dir, current_file)
                        print_message("\tWriting file: " + curr_qfn)
                        with open(curr_qfn, "w") as f:
                            f.write(sub)
                    else:
                        print_message("\tFailed to find the end of the file name.")
                        success = False
                else:
                    print_message("\tFailed to find the beginning of the file name.")
                    success = False
        else:
            print_message("\tFailed to find any file names in the completion.")
            success = False
    else:
        print_message("\tFailed to get a valid completion from OpenAI.", PrintDisposition.ERROR)
        success = False

    return success

def clean_up():
    print_message(Style.RESET_ALL)

def init_app(args):
    print_message("Initializing app...")

    global application_path
    global new_sample_output_dir

    if getattr(sys, 'frozen', False):
        application_path = os.path.dirname(sys.executable)
    elif __file__:
        application_path = os.path.dirname(__file__)

    new_sample_output_dir = os.path.join(application_path, 'outputs')

    if args.debug:
        print_message("Debugging enabled.", PrintDisposition.WARNING)
        global debug_mode
        debug_mode = True

def main():
    print_message()

    # Get the command-line args (parameters).
    args = parse_args()

    # Initialize the application.
    init_app(args)

    # If args are valid...
    if get_input_source(args):

        # Create the new sample.
        if create_new_sample():

            # Print success message to user.
            print_message(f"Sample successfully translated: {new_sample_input_dir}", PrintDisposition.SUCCESS)
        else:
            print_message(Fore.RED + 'Failed generation.' + Style.RESET_ALL)
    else:
        print_message(Fore.RED + 'Failed to get args.' + Style.RESET_ALL)

    clean_up()
main()