import sys
import os
import keyboard
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
SETTINGS_FILE_NAME              = 'settings.json'

openai.api_base     = OPENAI_API_BASE
openai.api_version  = OPENAI_VERSION

credential = AzureCliCredential()
token = credential.get_token("https://cognitiveservices.azure.com/.default")

openai.api_type     = OPENAI_API_TYPE
openai.api_key      = token.token
        
TEST_RECORD_FILE_NAME           = 'TestRecord.md'

# Globals
settings_before_and_after_dirs  = {}
directories_to_process          = []
sample_inputs_source            = []
sample_outputs_source           = []
debug_mode                      = False
debug_path                      = ''
temp_path                       = ''
new_sample_input_dir            = ''
new_sample_output_dir           = ''

class AppMode(Enum):
    PROCESS_ALL_SAMPLES_WITHOUT_INTERRUPTION    = 1
    CONFIRM_CONTINUE_AFTER_EACH_SAMPLE          = 2

app_mode = AppMode.CONFIRM_CONTINUE_AFTER_EACH_SAMPLE

class PrintDisposition(Enum):
    SUCCESS = 1
    WARNING = 2
    ERROR   = 3
    QUERY   = 4
    STATUS  = 5

def print_message(text = '', disp = PrintDisposition.STATUS):
    if disp == PrintDisposition.SUCCESS:
        color = Fore.GREEN
    elif disp == PrintDisposition.WARNING:
        color = Fore.YELLOW
    elif disp == PrintDisposition.ERROR:
        color = Fore.RED
    elif disp == PrintDisposition.QUERY:
        color = Fore.BLUE
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

def generate_new_sample(sample_dir):

    print_message("Generating new sample...")

    completion = ''

    try:
        print_message("\tCreating prompt...")

        messages = []

        for i in range(len(sample_inputs_source)-1):
            messages.append({"role": "user", "content": sample_inputs_source[i]})
            messages.append({"role": "assistant", "content": sample_outputs_source[i]})

        sample_source = get_terraform_source_code(sample_dir)
        messages.append({"role": "user", "content": sample_source})

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
            completion = response.user_responses[0].message.content.rstrip()
    except OSError as error:
        print_message(f"Failed to generate new sample. {error}", PrintDisposition.ERROR)

    time.sleep(1)

    if debug_mode:
        write_file('completion.txt', completion)
    
    return completion

def get_input_source(args):
    print_message("Validating input args...")

    for i, (before, after) in enumerate(settings_before_and_after_dirs.items()):
        sample_inputs_source.append(get_terraform_source_code(before))
        sample_outputs_source.append(get_terraform_source_code(after))

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

    argParser.add_argument("-r", 
                           "--recursive", 
                           action=argparse.BooleanOptionalAction,
                           help="Processes all subdirectories of specified 'input sample directory'.", 
                           required=False)

    argParser.add_argument("-d", 
                           "--debug", 
                           action=argparse.BooleanOptionalAction,
                           help="Outputs files to help with debugging.", 
                           required=False)

    return argParser.parse_args()

def create_new_sample(sample_dir):
    print_message("Creating new sample...")

    success = True

    completion = generate_new_sample(sample_dir)
    return

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
                        raise ValueError('Failed to find the end of the file name.')
                else:
                    raise ValueError('Failed to find the beginning of the file name.')
        else:
            raise ValueError('Failed to find any file names in the completion.')
    else:
        raise ValueError('Failed to get a valid completion from OpenAI.')

def init_app(args):
    print_message("Initializing app...")

    # Get the application path.
    application_path = ''
    if getattr(sys, 'frozen', False):
        application_path = os.path.dirname(sys.executable)
    elif __file__:
        application_path = os.path.dirname(__file__)

    # Verify that the application path was found.
    if application_path == '':
        raise ValueError('Failed to get application path.')

    # Set the debug path based on the application path.
    global debug_path
    debug_path = os.path.join(application_path, 'debug')

    # If debug path doesn't exist, create it.
    if not os.path.exists(debug_path):
        try:
            os.mkdir(debug_path)
        except OSError as error:
            raise ValueError('Failed to create debug directory.') from error
        
    # Set the temp path based on the application path.
    global temp_path
    temp_path = os.path.join(application_path, 'temp')

    # If temp path doesn't exist, create it.
    if not os.path.exists(temp_path):
        os.mkdir(temp_path)

    # Set global debugging flag based on command-line arg.        
    if args.debug:
        print_message("Debugging enabled.", PrintDisposition.WARNING)
        global debug_mode
        debug_mode = True

    get_before_and_after_sample_dirs()

    load_directories_to_process(args)

def get_before_and_after_sample_dirs():

    try:
        # Open the Inputs file.
        with open(SETTINGS_FILE_NAME) as inputs_file:
            # Load the JSON inputs file.
            inputs = json.load(inputs_file)
    except OSError as error:
        raise ValueError(f"Failed to open settings file ({SETTINGS_FILE_NAME}).") from error

    # Each line is an input and there needs to be at least one line (input).
    if 1 > len(inputs):
        raise ValueError('At least one input/output pair must be specified in the inputs file.')

    # For each line in the file (representing a sample)...
    for i, (input, output) in enumerate(inputs.items()):
        settings_before_and_after_dirs[input] = output

def load_directories_to_process(args):
    print_message("Loading directories to process...")

    global directories_to_process

    # If the specified sample dir exists...
    if file_exists(args.sample_directory):

        # If recursive flag is set...
        if args.recursive:

            # For every directory in the sample dir...
            for root, dirs, files in os.walk(args.sample_directory):

                # For every directory in the sample dir...
                for dir in dirs:

                    # Add the directory to the list.
                    if len([1 for x in list(os.scandir(os.path.join(root, dir))) if x.is_file()]) > 0:
                        directories_to_process.append(os.path.abspath(os.path.join(root, dir)))
    else:
        raise ValueError(f"Sample directory not found: {args.sample_directory}")

def present_plan():
    print_message()
    print_message("***IMPORTANT***: The Skilling org pays for the use of the Azure OpenAI service based on the number of tokens in the request & response for each generated sample.", PrintDisposition.WARNING)
    print_message("See the pricing article for more information: https://azure.microsoft.com/en-us/pricing/details/cognitive-services/openai-service/", PrintDisposition.WARNING)
    print_message("Please review the plan below and reach out for guidance if you think the number of samples might be costly.", PrintDisposition.WARNING)
    print_message()
    print_message("Plan:", PrintDisposition.WARNING)
    print_message()

    # Print the number of directories to process.
    print_message(f"\tNumber of directories to process (max 5 shown): {len(directories_to_process)}", PrintDisposition.WARNING)
    for i in range(len(directories_to_process)): 
        print_message(f"\t{i+1}: {directories_to_process[i]}", PrintDisposition.WARNING)
    print_message()

    print_message("\tThe following inputs pairs will be used to generate the new sample(s):", PrintDisposition.WARNING)
    for i, (before, after) in enumerate(settings_before_and_after_dirs.items()):
        print_message(f"\tBefore: {before}", PrintDisposition.WARNING)
        print_message(f"\tAfter: {after}", PrintDisposition.WARNING)
        print_message()

def confirm_continuation_for_current_sample(sample_dir):
    process_current_sample = True

    print_message("Are you sure you want to perform this action?", PrintDisposition.QUERY)
    print_message(f"Migrating sample directory: {sample_dir}", PrintDisposition.QUERY)
    print_message("[Y] Yes, process this sample [A] Yes to All, [No] Skip this sample, [Q] Quit the application.", PrintDisposition.QUERY)

    while True:
        user_response = keyboard.read_key().upper()

        global app_mode
        if user_response == "Y":
            process_current_sample = True
            break
        elif user_response == "A":
            app_mode = AppMode.PROCESS_ALL_SAMPLES_WITHOUT_INTERRUPTION
            process_current_sample = True
            break
        elif user_response == "N":
            process_current_sample = False
            break
        elif user_response == "Q":
            raise ValueError("User cancelled the application.")

        time.sleep(0.3)

    return process_current_sample

def main():
    try:
        # Get the command-line args (parameters).
        args = parse_args()

        # Initialize the application.
        init_app(args)

        # Present the plan to the user and allow them to cancel
        # or decide after each sample whether to continue.
        present_plan()

        # Get the source code for the samples that are being used as the prompt 
        # to illustrate the "before and after" samples.
        get_input_source(args)

        # For each directory to process...
        for sample_dir in directories_to_process:

            if (app_mode == AppMode.PROCESS_ALL_SAMPLES_WITHOUT_INTERRUPTION
            or confirm_continuation_for_current_sample(sample_dir)):

                # Create the new sample.
                create_new_sample(sample_dir)

                # Print success message to user.
                print_message(f"Sample successfully migrated: {sample_dir}", PrintDisposition.SUCCESS)

    except ValueError as error:
        print_message(f"Failed to migrate sample. {error}", PrintDisposition.ERROR)

main()